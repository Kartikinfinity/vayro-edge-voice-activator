#include "netstream.h"

#include <errno.h>
#include <inttypes.h>
#include <string.h>

#include "audio_ring.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"
#include "sdkconfig.h"
#include "serial_link.h"

#define MAGIC 0xA7
#define F_START 0x01
#define F_CONT 0x02
#define F_END 0x04
#define F_OVERRUN 0x08
#define F_PING 0x20
#define F_INFO 0x40
#define F_PONG 0x80
#define HDR 8
#define PKT_SAMPLES 640 /* 2 x 20 ms frames of 320 samples (§9.3, Architecture A) */
#define BIT_IP BIT0
#define N_CLK 8

static EventGroupHandle_t s_ev;
static SemaphoreHandle_t s_tx_mtx;
static QueueHandle_t s_trig_q;
static int s_sock = -1;
static volatile bool s_streaming;
static volatile bool s_server_end;
static volatile uint32_t s_active_id;
static volatile int64_t s_offset_us; /* server_us - device_us, from the lowest-RTT recent ping (IN-6) */
static volatile uint32_t s_rtt_us;
static volatile uint32_t s_pings;

static int send_all(int s, const uint8_t *p, size_t n)
{
    while (n) {
        int w = send(s, p, n, 0);
        if (w <= 0) {
            return -1;
        }
        p += w;
        n -= (size_t)w;
    }
    return 0;
}

static int send_pkt(uint8_t flags, uint16_t seq, const void *payload, size_t n)
{
    uint8_t buf[HDR + PKT_SAMPLES * 2];
    const uint32_t ms = (uint32_t)(esp_timer_get_time() / 1000);
    buf[0] = MAGIC;
    buf[1] = flags;
    buf[2] = 0; /* codec 0 = PCM16 */
    buf[3] = (uint8_t)seq;
    buf[4] = (uint8_t)(seq >> 8);
    buf[5] = (uint8_t)ms;
    buf[6] = (uint8_t)(ms >> 8);
    buf[7] = (uint8_t)(ms >> 16);
    if (n) {
        memcpy(buf + HDR, payload, n);
    }
    xSemaphoreTake(s_tx_mtx, portMAX_DELAY);
    const int r = s_sock >= 0 ? send_all(s_sock, buf, HDR + n) : -1;
    xSemaphoreGive(s_tx_mtx);
    return r;
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_ev, BIT_IP);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *e = (const ip_event_got_ip_t *)data;
        link_text("@NET wifi=up ip=" IPSTR "\n", IP2STR(&e->ip_info.ip));
        xEventGroupSetBits(s_ev, BIT_IP);
    }
}

static void wifi_init(void)
{
    esp_err_t e = nvs_flash_init();
    if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase()); /* NVS layout left over from the pre-existing Arduino image */
        e = nvs_flash_init();
    }
    ESP_ERROR_CHECK(e);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL, NULL));
    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, CONFIG_PS_WIFI_SSID, sizeof wc.sta.ssid);
    strlcpy((char *)wc.sta.password, CONFIG_PS_WIFI_PASSWORD, sizeof wc.sta.password);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());
#if CONFIG_PS_WIFI_PS_NONE
    /* Modem-sleep would delay server->device packets to DTIM boundaries and skew the clock-offset
     * estimate (asymmetric RTT); latency is a scored metric, power has no numeric target (§4.7). */
    esp_wifi_set_ps(WIFI_PS_NONE);
#endif
}

static void handle_pong(const uint8_t *p)
{
    static int64_t off[N_CLK];
    static uint32_t rtt[N_CLK];
    uint64_t t1, t2, t3;
    memcpy(&t1, p, 8);
    memcpy(&t2, p + 8, 8);
    memcpy(&t3, p + 16, 8);
    const int64_t t4 = esp_timer_get_time();
    const int64_t r = (t4 - (int64_t)t1) - (int64_t)(t3 - t2);
    const int64_t o = (((int64_t)t2 - (int64_t)t1) + ((int64_t)t3 - t4)) / 2;
    const uint32_t k = s_pings % N_CLK;
    off[k] = o;
    rtt[k] = r < 0 ? 0 : (uint32_t)r;
    s_pings++;
    uint32_t best = 0;
    const uint32_t n = s_pings < N_CLK ? s_pings : N_CLK;
    for (uint32_t i = 1; i < n; i++) {
        best = rtt[i] < rtt[best] ? i : best;
    }
    s_offset_us = off[best];
    s_rtt_us = rtt[best];
    struct {
        int64_t offset_us;
        uint32_t rtt_us;
        uint32_t pings;
    } info = {s_offset_us, s_rtt_us, s_pings};
    send_pkt(F_INFO, 0, &info, sizeof info);
}

static void net_task(void *arg)
{
    for (;;) {
        xEventGroupWaitBits(s_ev, BIT_IP, pdFALSE, pdTRUE, portMAX_DELAY);
        struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(CONFIG_PS_SERVER_PORT)};
        inet_pton(AF_INET, CONFIG_PS_SERVER_HOST, &a.sin_addr);
        const int s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (s < 0) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }
        if (connect(s, (struct sockaddr *)&a, sizeof a) != 0) {
            link_text("@NET tcp=connect_failed errno=%d server=%s:%d\n", errno, CONFIG_PS_SERVER_HOST,
                      CONFIG_PS_SERVER_PORT);
            close(s);
            vTaskDelay(pdMS_TO_TICKS(2000));
            continue;
        }
        const int one = 1;
        setsockopt(s, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        const struct timeval tv = {.tv_sec = 0, .tv_usec = 100000};
        setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
        xSemaphoreTake(s_tx_mtx, portMAX_DELAY);
        s_sock = s;
        xSemaphoreGive(s_tx_mtx);
        link_text("@NET tcp=connected server=%s:%d\n", CONFIG_PS_SERVER_HOST, CONFIG_PS_SERVER_PORT);

        uint8_t rx[128];
        size_t rn = 0;
        int64_t next_ping = 0;
        uint32_t sent_pings = 0;
        for (;;) {
            const int64_t now = esp_timer_get_time();
            if (now >= next_ping) {
                const uint64_t t1 = (uint64_t)now;
                if (send_pkt(F_PING, 0, &t1, sizeof t1)) {
                    break;
                }
                sent_pings++;
                next_ping = now + (sent_pings < 8 ? 500000 : 10000000); /* fast start, then 10 s keepalive */
            }
            const int r = recv(s, rx + rn, sizeof rx - rn, 0);
            if (r == 0) {
                break;
            }
            if (r < 0) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) {
                    continue;
                }
                break;
            }
            rn += (size_t)r;
            while (rn >= HDR) {
                if (rx[0] != MAGIC) {
                    memmove(rx, rx + 1, --rn);
                    continue;
                }
                const size_t need = rx[1] == F_PONG ? 24 : (rx[1] == F_END ? 4 : 0);
                if (rn < HDR + need) {
                    break;
                }
                if (rx[1] == F_PONG) {
                    handle_pong(rx + HDR);
                } else if (rx[1] == F_END) {
                    uint32_t id;
                    memcpy(&id, rx + HDR, 4);
                    if (id == s_active_id) {
                        s_server_end = true;
                    }
                }
                memmove(rx, rx + HDR + need, rn - HDR - need);
                rn -= HDR + need;
            }
        }
        xSemaphoreTake(s_tx_mtx, portMAX_DELAY);
        s_sock = -1;
        xSemaphoreGive(s_tx_mtx);
        close(s);
        link_text("@NET tcp=closed\n");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

static void streamer_task(void *arg)
{
    static int16_t pcm[PKT_SAMPLES];
    uint32_t activation = 0;
    for (;;) {
        ns_trigger_t t;
        xQueueReceive(s_trig_q, &t, portMAX_DELAY);
        activation++;
        s_server_end = false;
        s_active_id = activation;
        uint32_t r = t.trig_sample - (uint32_t)CONFIG_PS_PREROLL_MS * 16;
        struct __attribute__((packed)) {
            uint32_t activation, kw_frame;
            uint64_t t_detect_us;
            uint32_t preroll_ms, first_sample;
            int8_t raw;
            uint8_t pad[3];
            uint32_t reserved;
        } st = {activation, t.kw_frame, (uint64_t)t.t_detect_us, CONFIG_PS_PREROLL_MS, r, t.raw, {0}, 0};
        const int64_t t_start_tx = esp_timer_get_time();
        int ok = send_pkt(F_START, 0, &st, sizeof st) == 0;
        uint16_t seq = 1;
        uint32_t sent = 0, min_slack = RING_SAMPLES, reason = ok ? 0 : 4;
        int64_t t_audio0_tx = 0;
        const int64_t t_stop = t.t_detect_us + (int64_t)CONFIG_PS_STREAM_MAX_MS * 1000;
        while (ok) {
            if (s_server_end) {
                reason = 1; /* server endpointing */
                break;
            }
            if (esp_timer_get_time() > t_stop) {
                reason = 2; /* device hard timeout */
                break;
            }
            const uint32_t backlog = ring_w() - r;
            if (backlog >= RING_SAMPLES) {
                send_pkt(F_OVERRUN, seq, NULL, 0);
                reason = 3; /* lapped: a short correct stream beats a long corrupt one (§8.5) */
                break;
            }
            if (RING_SAMPLES - backlog < min_slack) {
                min_slack = RING_SAMPLES - backlog;
            }
            if (backlog < PKT_SAMPLES) {
                vTaskDelay(pdMS_TO_TICKS(5));
                continue;
            }
            if (!ring_read(r, pcm, PKT_SAMPLES)) {
                send_pkt(F_OVERRUN, seq, NULL, 0);
                reason = 3;
                break;
            }
            if (!t_audio0_tx) {
                t_audio0_tx = esp_timer_get_time();
            }
            if (send_pkt(F_CONT, seq++, pcm, sizeof pcm)) {
                reason = 4; /* socket error */
                break;
            }
            r += PKT_SAMPLES;
            sent += PKT_SAMPLES;
        }
        struct {
            uint32_t activation, samples_sent, min_slack_samples, reason;
        } en = {activation, sent, min_slack, reason};
        send_pkt(F_END, seq, &en, sizeof en);
        link_text("@STREAM act=%" PRIu32 " reason=%" PRIu32 " sent_ms=%" PRIu32 " min_slack_ms=%" PRIu32
                  " t_detect_us=%" PRId64 " start_tx_us=%" PRId64 " audio0_tx_us=%" PRId64 " offset_us=%" PRId64
                  " rtt_us=%" PRIu32 "\n",
                  activation, reason, sent / 16, min_slack / 16, t.t_detect_us, t_start_tx, t_audio0_tx, s_offset_us,
                  s_rtt_us);
        s_streaming = false;
    }
}

bool ns_connected(void)
{
    return s_sock >= 0;
}

bool ns_trigger(const ns_trigger_t *t)
{
    if (!ns_connected() || s_streaming) {
        return false;
    }
    s_streaming = true;
    return xQueueSend(s_trig_q, t, 0) == pdTRUE;
}

esp_err_t ns_start(void)
{
    s_ev = xEventGroupCreate();
    s_tx_mtx = xSemaphoreCreateMutex();
    s_trig_q = xQueueCreate(1, sizeof(ns_trigger_t));
    wifi_init();
    xTaskCreatePinnedToCore(net_task, "netlink", 4096, NULL, 10, NULL, 0);
    xTaskCreatePinnedToCore(streamer_task, "streamer", 4096, NULL, 12, NULL, 0);
    return ESP_OK;
}

/* SS-9 · instrument — memory probes (S-scopes) and boot identity, emitted as @-prefixed
 * key=value TEXT lines that host/capture.py parses into device_events.jsonl. */
#pragma once

/* One "@MEM" line: internal-RAM heap totals, free, minimum-ever free, largest block. */
void inst_mem_report(const char *tag);

/* One "@BOOT" line: IDF version, firmware ELF SHA-256 prefix, chip, flash, PSRAM policy, reset reason. */
void inst_boot_report(void);

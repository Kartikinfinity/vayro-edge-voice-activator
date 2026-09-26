cmake_minimum_required(VERSION 3.16)

# PS26172 edge firmware (ESP32-S3 + INMP441). ESP-IDF v5.5.5 — see docs/PROJECT_STATE.md.
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(ps26172_fw)

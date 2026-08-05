# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Prepare repository, documentation, diagnostics, and entity-registry cleanup for the first stable release.

## 0.3.11-test

- Consolidated every received BLE packet into one structured DEBUG log line.
- Classified normal scale disconnects as reconnect events rather than integration failures.
- Treated unknown-user and incomplete measurements as ignored cycles rather than persistent errors.
- Correctly recognized the repeated final frame of a bootstrap-rejected measurement as a duplicate.

## 0.3.10-test

- Removed synthetic Cancel and Back radio options from profile selection forms.
- Rejected a complete measurement cycle when it began before reconnect/bootstrap reached `ready`.

## 0.3.9-test

- Restored reliable reconnect after a remote power loss.
- Retained one fresh BLE client and one notification callback per session.

## 0.3.8-test

- Added explicit session, callback, and notification counters while investigating accumulated callbacks.
- Disabled GATT service-cache reuse for reconnect testing.

## 0.3.7-test

- Removed the broad config-entry update listener that could reload the integration during a measurement.
- Limited reloads to completed options changes.

## 0.3.6-test

- Allocated profile UIDs only from the verified safe range `0x1001..0x7FFF`.

## 0.3.4-test

- Added independent Add, Edit, and Delete profile flows while preserving stable profile UIDs.

## 0.3.2-test

- Added optional local BlueZ connection-parameter optimization and stale-session isolation.

## 0.3.0

- Replaced advertisement-triggered sessions with one persistent GATT connection.
- Added bootstrap commands, live profile recognition, automatic reconnect, and repeated-final filtering.

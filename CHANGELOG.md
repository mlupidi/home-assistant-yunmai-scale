# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- `Connection` switch. Turning it off closes the BLE connection and stops
  advertisement tracking so the scale can sleep; turning it on reconnects.
  The state is restored after a restart, so a schedule helper and an
  automation can keep the scale connected only during the hours it is used.
  While paused, the session status sensor reports `paused`.

## 0.4.2 - 2026-08-06

### Fixed

- Removed the custom integration's exact `bleak-retry-connector` requirement.
  Home Assistant Core already provides this library through the built-in
  Bluetooth integration.
- Declared the built-in `bluetooth` integration as a dependency so Yunmai Scale
  uses the compatible library version bundled with the installed Home
  Assistant release.
- Fixed startup failure after Home Assistant updated
  `bleak-retry-connector` from 4.6.1 to 4.6.3.

## 0.4.1 - 2026-08-06

### Added

- Diagnostic Bluetooth signal-strength sensor using the RSSI from the latest
  scale advertisement, allowing Home Assistant history graphs.
- Recent advertisement RSSI statistics in downloadable diagnostics: last,
  minimum, maximum, average, sample count, total advertisement count, and age
  of the last advertisement.

### Changed

- A fresh connectable scale advertisement now interrupts reconnect backoff,
  including the 30-second maximum delay, so reconnection starts immediately
  when the scale becomes reachable.

## 0.4.0 - 2026-08-05

First public release.

### Added

- Persistent local BLE connection with automatic reconnect.
- Multi-profile recognition and scale-side profile switching.
- Weight, body-fat, last-measurement, raw-impedance, last-user, and session
  status entities.
- Profile add, edit, and delete flows with stable profile UIDs.
- Automatic Entity Registry cleanup for deleted profiles.
- Optional local BlueZ connection-parameter optimization.
- English and Russian translations.
- Privacy-safe downloadable diagnostics.
- Local Home Assistant brand icon.
- HACS-compatible repository structure and validation workflows.

### Changed

- BLE reconnect lifecycle now uses one client and one notification callback per
  session.
- Measurements that begin before reconnect/bootstrap reaches `ready` are
  ignored as a complete cycle.
- Normal disconnects, unknown users, and incomplete measurements are logged as
  expected operating conditions rather than persistent integration errors.
- BLE session/callback counters are available in diagnostics instead of normal
  entity attributes.

### Verified

- `YUNMAI-SIGNAL-CW`
- Home Assistant OS 18.2
- Home Assistant Core 2026.7.4
- Raspberry Pi 4 with a local Bluetooth adapter
- Manual installation and HACS custom-repository installation
- Reconnect after scale power loss
- Multiple configured profiles

## 0.3.14-test

- Restored `custom_components/yunmai_scale/brand/icon.png` in the installation
  archive.
- No BLE or measurement behavior changes.

## 0.3.13-test

- Added Home Assistant config-entry diagnostics.
- Redacted the Bluetooth address and complete profile configuration.
- Excluded names, birth information, reference weights, and body measurements.
- Removed temporary BLE callback counters from normal entity attributes.

## 0.3.12-test

- Removed orphaned profile entities from the Entity Registry during setup and
  options reload.
- Preserved shared status and last-user entities.

## 0.3.11-test

- Consolidated each received BLE packet into one structured DEBUG line.
- Classified normal scale disconnects as reconnect events.
- Treated unknown-user and incomplete measurements as ignored cycles rather
  than persistent errors.
- Correctly classified the repeated final frame of a bootstrap-rejected
  measurement as a duplicate.

## 0.3.10-test

- Removed synthetic Cancel and Back radio choices from profile-selection forms.
- Rejected a complete measurement cycle when it began before reconnect/bootstrap
  reached `ready`.

## 0.3.9-test

- Restored reconnect after remote scale power loss.
- Retained one fresh BLE client and one notification callback per session.

## 0.3.8-test

- Added explicit session/callback diagnostics while investigating accumulated
  notification subscriptions.
- Disabled GATT service-cache reuse for reconnect testing.

## 0.3.7-test

- Removed the broad config-entry update listener that could reload the
  integration during a measurement.
- Limited reloads to completed options changes.

## 0.3.6-test

- Allocated profile UIDs only from the verified safe range `0x1001..0x7FFF`.

## 0.3.4-test

- Added independent Add, Edit, and Delete profile flows while preserving stable
  profile UIDs.

## 0.3.2-test

- Added optional local BlueZ connection-parameter optimization.
- Added stale-session isolation.

## 0.3.0

- Replaced advertisement-triggered sessions with one persistent GATT
  connection.
- Added bootstrap commands, live profile recognition, automatic reconnect, and
  repeated-final filtering.

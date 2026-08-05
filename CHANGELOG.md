# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- HACS-compatible repository structure and validation workflows.
- English and Russian translations.
- Local Home Assistant brand icon.
- Privacy-safe downloadable diagnostics.
- Automatic Entity Registry cleanup for deleted profiles.

### Changed

- Repository documentation rewritten for installation, compatibility,
  diagnostics, and known limitations.
- BLE session/callback counters moved from normal entity attributes into the
  downloadable diagnostic report.

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

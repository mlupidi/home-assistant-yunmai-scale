# Yunmai Scale for Home Assistant

A local Home Assistant custom integration for compatible Yunmai Bluetooth body
scales. It maintains a persistent BLE connection, recognizes configured users
from live weight, sends the selected profile to the scale, and publishes the
final measurement without using the Yunmai cloud.

![Yunmai Scale icon](custom_components/yunmai_scale/brand/icon.png)

## Features

- Local BLE communication; no Yunmai account or cloud connection required.
- Persistent connection with automatic reconnect after a real BLE link loss.
- Multiple user profiles with stable profile IDs.
- User recognition from a stable live-weight window.
- Weight, scale-reported body-fat value, last measurement time, and optional
  raw impedance entities.
- Latest final weight becomes the user's next recognition reference.
- Profile add, edit, and delete flows.
- Automatic removal of orphaned entities when a profile is deleted.
- English and Russian interface translations.
- Privacy-safe downloadable diagnostics.
- Optional per-device BLE connection-parameter optimization for local BlueZ
  adapters.

## Compatibility

### Verified

- Scale: `YUNMAI-SIGNAL-CW`
- Protocol characteristics: `FFE4` notifications and `FFE9` writes
- Home Assistant OS 18.2
- Home Assistant Core 2026.7.4
- Raspberry Pi 4 with a local Bluetooth adapter

### Discovery candidates, not yet verified

The integration also advertises discovery support for these Yunmai names:

- `YUNMAI-ISM*`
- `YUNMAI-ISC2P*`
- `YUNMAI-Scale-3`
- `YUNMAI-ISSE*`

These names do not guarantee protocol compatibility. Please attach diagnostics
and debug logs when reporting another model.

## Installation through HACS

Until this repository is included in the default HACS catalog, add it as a
custom repository:

1. Open HACS.
2. Open the HACS menu and select **Custom repositories**.
3. Add:

   ```text
   https://github.com/Taxom/home-assistant-yunmai-scale
   ```

4. Select **Integration** as the category.
5. Find **Yunmai Scale** in HACS and download it.
6. Restart Home Assistant.
7. Open **Settings → Devices & services → Add integration → Yunmai Scale**.

For pre-release testing, select the repository's default branch when HACS
offers a version choice.

## Manual installation

Copy:

```text
custom_components/yunmai_scale
```

to:

```text
/config/custom_components/yunmai_scale
```

Restart Home Assistant, then add **Yunmai Scale** from
**Settings → Devices & services**.

When upgrading manually, replace the entire `yunmai_scale` directory instead of
merging individual files.

## Configuration

Wake the scale so Home Assistant can discover it, then create at least one user
profile.

Each profile contains:

- display name;
- height;
- birth year;
- sex value expected by the scale protocol;
- reference weight;
- athletic / extreme activity flag.

The reference weight is updated after each accepted final measurement.

### Recognition defaults

- nearest profile within ±10%;
- at least 2 kg closer than the second-best profile;
- 3 consecutive matching frames;
- no more than 0.8 kg spread across the stable window.

These rules are intentionally conservative. Users with similar weights may not
be distinguishable safely.

## Entities

For each profile:

- weight;
- body fat reported by the scale;
- last measurement timestamp;
- raw impedance, disabled by default and categorized as diagnostic.

Shared entities:

- last recognized user;
- session status.

The body-fat value is calculated by the scale firmware. This integration does
not claim medical accuracy.

## Bluetooth behavior

The integration keeps one BLE connection open and reconnects after an actual
disconnect. A scale normally accepts only one active BLE client, so close or
disable other applications and Home Assistant instances that may connect to it.

### Power optimization

The optional power optimization applies Linux/BlueZ connection parameters only
to the configured scale on a **local** Bluetooth adapter.

Available modes:

- Disabled;
- Moderate;
- Maximum tested;
- Custom.

The tested maximum preset uses a 45 ms connection interval, peripheral latency
19, and a 12 s supervision timeout. The optimization is skipped when the
connection is not through a supported local BlueZ adapter or when the required
management access is unavailable. Measurement continues with controller
defaults in that case.

Bluetooth proxy operation has not yet been validated. Low-level power
optimization is not applied through a proxy.

## Status values

- `starting`
- `waiting_for_bluetooth`
- `connecting`
- `reconnecting`
- `ready`
- `measuring`

An unknown user or incomplete measurement is ignored without deliberately
disconnecting the scale.

## Diagnostics and privacy

Use **Download diagnostics** from the integration menu when reporting a
problem. The report includes connection state, recognition settings, BLE power
status, session/callback counters, and profile/measurement counts.

The report redacts the Bluetooth address and profile definitions. It excludes
profile names, birth information, reference weights, and actual body
measurements.

## Debug logging

Enable temporarily in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.yunmai_scale: debug
    bleak_retry_connector: debug
```

Restart Home Assistant, reproduce the problem, then disable debug logging.

## Known limitations

- Only `YUNMAI-SIGNAL-CW` has been verified with real measurements.
- A persistent BLE connection uses more battery than advertising-only
  operation; the optional local BlueZ optimization reduces idle link activity.
- Battery level is not exposed: the tested scale has no standard BLE Battery
  Service and no confirmed battery field in its known protocol frames.
- Native Windows or macOS installations are not supported targets.
- Other Home Assistant versions and installation types have not yet completed
  the same validation matrix.

## Support

Open an issue and include:

- exact scale model and advertised Bluetooth name;
- Home Assistant version and installation type;
- local adapter or Bluetooth proxy;
- downloaded diagnostics;
- relevant debug log section.

Do not publish unredacted profile data or full Home Assistant storage files.

## License

MIT

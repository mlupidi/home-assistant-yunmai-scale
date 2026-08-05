# Contributing

Bug reports, protocol captures from additional Yunmai models, translations, and code improvements are welcome.

Before opening a pull request:

1. Keep all runtime integration files inside `custom_components/yunmai_scale/`.
2. Preserve backward compatibility for existing config entries and entity unique IDs.
3. Do not add speculative writes to unknown GATT characteristics.
4. Run Python syntax checks and validate all JSON files.
5. Explain the hardware and Home Assistant installation used for testing.

Never include private Home Assistant diagnostics, access tokens, precise personal measurements, or unredacted logs in a public issue.

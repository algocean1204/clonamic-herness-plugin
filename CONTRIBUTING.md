# Contributing

Open an issue before changing a public contract or adding a new module. Small bug fixes and documentation corrections may go directly to a pull request.

Every behavioral change needs a test that fails before the change and passes after it. Run:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --all-targets
python3 -m unittest discover -s tests -v
```

Keep platform adapters thin. Policy belongs in one skill or the Rust core, never copied across adapters. Do not add automatic external-model selection, memory collection, telemetry, credentials, or user-specific paths.

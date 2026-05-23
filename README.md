# Dangbei Tank

`dangbei-tank` is the source repository for the Dangbei/Mijia fish tank local-control solution.

Current status: design phase only. This repository does not yet contain the runnable gateway or Home Assistant integration.

The implementation target is:

- Unraid hosts the local MQTT broker and fish-tank gateway
- Home Assistant installs `dangbei_tank` through HACS
- the official mobile app remains usable through vendor-cloud passthrough

Primary design document:

- [docs/design.md](docs/design.md)

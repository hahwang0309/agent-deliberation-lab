# Frozen experimental implementation

`frozen-experiment.tar` is copied byte-for-byte from the first reproduction release. It records source commit `7a244351f3374b3e1ac4b02bf55a4f41ff9ca91c`, before the later analysis and adjudication work. It preserves historical experiment source/configuration, not private raw databases, credentials, or an assurance that historical hosted models remain available.

Inspect with `tar -tf experiment/frozen-experiment.tar`; extract into a separate directory. This archive is not needed for the offline quick start. Do not use current platform defaults as the experimental settings: the public dataset supplies `experiment-settings.yaml` and `experiment-prompt-templates.yaml`.

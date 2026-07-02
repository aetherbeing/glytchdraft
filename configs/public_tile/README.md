# Public Tile Staging Templates

This directory contains provider-neutral Atlantid templates for a future
one-tile Beachhead Proof package. They are not real Miami outputs and do not
authorize deployment.

Use `static_asset_layout.template.json` as the layout rule set for the future
smoke-validated tile package. The eventual package must contain only relative
paths, computed file hashes, explicit cache policies, and auditable publication
gate evidence.

The actual GlitchOS viewer belongs in the separate `glytchOS` repository. This
repository prepares the static artifacts and receipts that GlitchOS will consume.

After the controlled smoke, determinism run, contract integration, and
publication gates pass, insert the approved tile outputs into a package root and
run:

```bash
python scripts/validate_public_tile_package.py \
  --layout configs/public_tile/static_asset_layout.template.json \
  --package-root <future-package-root>
```

No unconfirmed source is included in this artifact.

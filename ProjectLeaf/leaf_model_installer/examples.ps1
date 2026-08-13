# LeafOS Model Installer examples, v0.4.0

# Bootstrap tooling only.
.\install.ps1

# Local-only inspection.
.\leaf-models.cmd catalog
.\leaf-models.cmd doctor

# Create an offline plan for primary + secondary coders.
.\leaf-models.cmd plan --profile default --out .\leaf-model-plan.json

# Create an offline plan for the empty-input LeafOS runtime.
.\leaf-models.cmd plan --profile runtime-default --out .\leaf-runtime-plan.json

# Resolve exact files and pin repository revisions. Metadata only.
.\leaf-models.cmd resolve .\leaf-model-plan.json
.\leaf-models.cmd show .\leaf-model-plan.resolved.json

# Download boundary. Run only after reviewing the resolved plan.
.\leaf-models.cmd apply .\leaf-model-plan.resolved.json --yes

# Local verification later.
.\leaf-models.cmd verify .\leaf-model-plan.resolved.json

# Extended plan with the explicit slot-4 fallback policy enabled.
.\leaf-models.cmd plan --profile extended --allow-fallback --out .\leaf-model-extended.json

# Experimental heavyweight requires explicit selection and two apply guards.
.\leaf-models.cmd plan --slot 5 --out .\leaf-model-heavy.json
# .\leaf-models.cmd resolve .\leaf-model-heavy.json
# .\leaf-models.cmd apply .\leaf-model-heavy.resolved.json --yes --include-experimental --confirm-heavy gpt-oss-120b

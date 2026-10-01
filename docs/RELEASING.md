# Versions, tags, and distribution

## Version identity

The current version is `1.0.0-rc3`. It must remain consistent across `package.json`, `web/package.json`, `.codex-plugin/plugin.json`, the OmniStream Bridge extension, and `release-manifest.json`. The `-rc3` suffix denotes a candidate, not stable certification.

Git tags use the form `v<version>`, for example `v1.0.0-rc3`. A tag must point to the commit reviewed and qualified for that version. The [release checklist](RELEASE-CHECKLIST.md) defines the checks required before a candidate tag or promotion to `1.0.0`.

Status checked on October 1, 2026: the repository has no GitHub tag or GitHub Release. The npm package remains unpublished (`private: true`). Candidate archives are built and verified locally; this document does not present those local artifacts as public downloads.

## Downloadable artifact

OmniStream provides a Windows source-only archive, not a prebuilt NVIDIA runtime. Build it from the repository root with:

```powershell
.\installer\Build-Release.ps1
```

The output is placed under `release/` as `omnistream-for-codex-<version>.zip` and `omnistream-for-codex-<version>.zip.sha256`. The ZIP contains OmniStream source, the installer, tests, and documentation. Kit, the NVIDIA WebRTC SDK, their caches, and the panel bundle are obtained or built on the target machine.

After extraction, verify the strict manifest:

```powershell
npm run verify:release -- --strict
```

SHA-256 and the manifest attest that files match the supplied values; they are neither a digital signature nor a provenance certification.

Git attributes keep source text in LF form on Windows, so checkout conversion does not invalidate source-file hashes. Regenerate the manifest after changing any distributed source or documentation; the manifest does not hash itself.

## Registry packages and licence

`package.json` describes the repository, its keywords, support, and scope. It keeps `private: true` and `license: UNLICENSED`; no npm package is published. Do not remove this protection or assign a licence without a decision by the rights holder. Public repository visibility does not grant rights to reuse or redistribute the software.

A GitHub Release for a candidate must be marked **Pre-release**, use a tag that matches the version, and attach the ZIP and its `.sha256` file. Do not announce a stable release until the [validation](VALIDATION.md) and [licensing](PUBLIC-DEPLOYMENT.md) gates have been met.

## CI

The repository currently contains no versioned GitHub Actions workflow. Until a workflow is added and a run is observed, describe source and installation commands as local checks.

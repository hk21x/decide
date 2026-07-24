# Unraid Community Applications templates — hk21x

Docker templates for [Unraid Community Applications](https://unraid.net/community/apps).

| App | Template | Project |
|---|---|---|
| **decide** — swipe-to-match film picker for Plex | [templates/decide.xml](templates/decide.xml) | [hk21x/decide](https://github.com/hk21x/decide) |

## Submitting / updating (maintainer notes)

This directory mirrors the layout of the
[unraid-community-apps-starter](https://github.com/unraid/unraid-community-apps-starter)
and is intended to live as its own **public** repository
(`hk21x/unraid-templates` — if you pick a different name, update
`TemplateURL` in each template and `Icon` in `ca_profile.xml` to match).

1. Push this directory as the root of `github.com/hk21x/unraid-templates`.
2. Make sure the decide image is public on GHCR
   (`ghcr.io/hk21x/decide:latest` must pull without auth).
3. Go to <https://ca.unraid.net/submit/new>, enter the repository URL, and
   run the validation scan.
4. Submit for review once all checks pass.

Template changes after acceptance are picked up automatically from `main` —
no re-submission needed.

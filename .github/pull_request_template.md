## Що змінено

<!-- коротко: поведінка, компонент, розгортання -->

## Definition of Done — docs-or-don't-merge

Змінює публічну поведінку (ендпоінт, формат відповіді, код помилки, конфігурацію)? Тоді в цьому PR:

- [ ] `docs/api/openapi.yaml` оновлено, `info.version` підвищено за SemVer; Spectral — 0 errors
- [ ] contract-тест Schemathesis проти запущеного API — 0 failures
- [ ] зачеплені сторінки `docs/` (SDD / ISD / runbook / ADR) оновлено, у front matter — `owner`, `status`, `review_date`
- [ ] запис у `CHANGELOG.md`
- [ ] `markdownlint-cli2` і `mkdocs build --strict` — зелені (конвеєр `Docs`)
- [ ] Документацію оновлювати не потрібно, бо: <!-- причина; погоджує власник з CODEOWNERS -->

Повний чек-лист — `docs/developer/CONTRIBUTING.md` → «Definition of Done».

---
title: Довідка API (Swagger UI)
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [api]
---

# Довідка API — рендериться з `openapi.yaml`

Інтерактивна довідка нижче будується в браузері з файлу [`openapi.yaml`](openapi.yaml) — того самого, що
лінтує Spectral і з якого генерується SDK. **Try it out** надсилає запит на сервер з розділу `servers`
(`http://localhost:8000` — sandbox із README); щоб браузер дозволив виклик з цього сайту, API запускають з
`CORS_ALLOW_ORIGINS=<адреса сайту>` (див. [[contract-testing]]).

<swagger-ui src="openapi.yaml"/>

Пов'язано: [[api-overview]] · [[contract-testing]] · #api

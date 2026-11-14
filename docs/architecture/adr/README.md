# Architecture Decision Records

Рішення фіксується в момент прийняття і **не переписується заднім числом**: застаріле отримує статус
`Superseded by ADR-NNNN`, нове рішення — новий номер.

| № | Рішення | Статус |
|---|---|---|
| [0001](0001-postgresql-redis-rabbitmq-storage.md) | PostgreSQL як джерело істини, Redis — гарячий стан, RabbitMQ — телеметрія | Accepted |
| [0002](0002-gitops-argo-canary-delivery.md) | GitOps (Argo CD) + canary Argo Rollouts з автоматичним відкатом за метриками | Accepted |

## Шаблон

```markdown
# ADR-NNNN: <рішення>
- **Статус:** Proposed | Accepted | Deprecated | Superseded by ADR-NNNN
- **Дата рішення:** YYYY-MM-DD
- **Автор / власник:**
## Контекст
## Розглянуті альтернативи
## Рішення
## Наслідки
```

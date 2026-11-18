| row uses col | c0 | c1 | c2 | c3 | c4 | c5 | c6 | c7 | c8 | c9 | c10 | c11 | c12 | c13 | c14 | c15 | c16 | c17 | c18 | c19 | c20 | c21 | c22 | c23 | c24 | c25 | c26 | out |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c0 AuditPort |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c1 BasePricing |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c2 BillingPort |  |  |  |  |  |  |  |  | X |  |  |  |  |  | X |  |  |  |  | X |  |  |  |  |  |  |  | 3 |
| c3 BillingService |  |  |  |  |  |  |  |  | X |  |  |  |  |  | X |  |  |  |  | X |  |  |  | X |  |  |  | 4 |
| c4 Clock |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c5 CorporatePricing |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | X | 1 |
| c6 FineCalculator |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c7 FleetPort |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | X |  | 1 |
| c8 Invoice |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c9 LedgerPort |  |  |  |  |  |  |  |  |  |  |  |  |  |  | X |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| c10 MailPort |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c11 Mailer |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c12 NotificationService |  |  |  |  |  |  |  |  | X |  | X |  |  |  | X |  |  |  | X |  |  |  |  |  |  |  |  | 4 |
| c13 RentalLifecycleService | X |  |  |  |  |  |  | X |  | X |  |  |  |  | X |  |  |  | X |  |  | X |  |  |  |  |  | 6 |
| c14 RentalRecord |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c15 RentalStore |  |  |  |  | X |  |  |  |  |  |  |  |  |  | X |  |  |  |  |  |  |  |  |  |  |  |  | 2 |
| c16 RentalSystem |  |  |  | X |  |  |  | X |  | X |  | X | X | X |  |  |  |  |  |  | X | X |  |  |  |  |  | 8 |
| c17 RenterDirectory |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | X |  |  |  |  |  |  |  | 1 |
| c18 RenterPort |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | X |  |  |  |  |  |  |  | 1 |
| c19 RenterRecord |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c20 ReportingService |  |  | X |  |  |  |  | X |  | X |  |  |  |  | X |  |  |  | X |  |  |  |  |  |  |  |  | 5 |
| c21 StationPort |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c22 TariffCalculator |  |  |  |  |  |  | X |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| c23 TariffPort |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c24 VehicleFleet |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | X |  | 1 |
| c25 VehicleRecord |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 |
| c26 WeekendPricing |  | X |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| in | 1 | 1 | 1 | 1 | 1 | 0 | 1 | 3 | 3 | 3 | 1 | 1 | 1 | 1 | 7 | 0 | 0 | 0 | 3 | 4 | 1 | 2 | 0 | 1 | 0 | 2 | 1 | |

```mermaid
graph LR
  BillingPort --> Invoice
  BillingPort --> RentalRecord
  BillingPort --> RenterRecord
  BillingService --> Invoice
  BillingService --> RentalRecord
  BillingService --> RenterRecord
  BillingService --> TariffPort
  CorporatePricing --> WeekendPricing
  FleetPort --> VehicleRecord
  LedgerPort --> RentalRecord
  NotificationService --> Invoice
  NotificationService --> MailPort
  NotificationService --> RentalRecord
  NotificationService --> RenterPort
  RentalLifecycleService --> AuditPort
  RentalLifecycleService --> FleetPort
  RentalLifecycleService --> LedgerPort
  RentalLifecycleService --> RentalRecord
  RentalLifecycleService --> RenterPort
  RentalLifecycleService --> StationPort
  RentalStore --> Clock
  RentalStore --> RentalRecord
  RentalSystem --> BillingService
  RentalSystem --> FleetPort
  RentalSystem --> LedgerPort
  RentalSystem --> Mailer
  RentalSystem --> NotificationService
  RentalSystem --> RentalLifecycleService
  RentalSystem --> ReportingService
  RentalSystem --> StationPort
  RenterDirectory --> RenterRecord
  RenterPort --> RenterRecord
  ReportingService --> BillingPort
  ReportingService --> FleetPort
  ReportingService --> LedgerPort
  ReportingService --> RentalRecord
  ReportingService --> RenterPort
  TariffCalculator --> FineCalculator
  VehicleFleet --> VehicleRecord
  WeekendPricing --> BasePricing
```

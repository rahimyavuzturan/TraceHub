---
type: service
title: "Mobil Şube Web"
aliases: ["mobil şube", "msube", "mobil banka", "mobil uygulama"]
tags: ["mobil", "boa", "dmz"]
owner: "DevOps"
updated: 2026-09-30
confidence: high

repository:
  platform: azure-devops
  project: "KT"
  path: "KT/BOA/msube-web"

deployments:
  - environment: prod
    cluster: prod-cluster
    namespace: mobile
    workload: msube-web
    kind: Deployment
  - environment: dmz-preprod
    cluster: dmz-cluster
    namespace: dmz-mobile-prep
    workload: msube-web
    kind: Deployment

observability:
  elastic_indices: ["msube-web-*"]
  grafana_dashboards: ["Mobil Şube Genel"]
  log_format: json
  correlation_field: "traceId"

network:
  netscaler_vservers: ["vs_msube_prep_443"]
  ingress_hosts: ["msubetest.kuveytturk.com.tr"]

depends_on: ["boa-integration"]

contacts:
  - team: "Mobil Uygulama Geliştirme"
    channel: "Teams / Mobil Ekip"
---

# Mobil Şube Web

Müşterilerin mobil uygulamadan yaptığı istekleri karşılayan web katmanı.
İstekleri doğrudan çözmez; iş mantığı için `boa-integration` servisine gider.

> Bu doküman bir örnektir. Gerçek ortam değerleriyle güncellenmelidir.

## Loglar

Uygulama JSON formatında `stdout`'a loglar, ELK'de `msube-web-*` index'inde toplanır.
Korelasyon alanı `traceId` — bir isteği katmanlar boyunca takip etmek için bu alanı kullanın.

Sık görülen hatalar:

- `BackendTimeoutException` — integration katmanına 5 saniyede ulaşılamadı.
  Genellikle sorun bu serviste değil, `boa-integration` veya arkasındaki backend'dedir.
- `KeyNotFoundException` — ConfigMap'te beklenen anahtar yok. Pod açılışta kapanır,
  `CrashLoopBackOff` durumuna geçer.

## Sağlık kontrolü

`/health/ready` uç noktası backend bağlantısını da kontrol eder; bu yüzden backend
sorunlarında pod `Ready` olmaz ama `Running` kalır. Pod durumuna bakarken
`READY` sütununu ihmal etmeyin.

## Dikkat edilecekler

DMZ ve iç ortam ayrı cluster'lardadır. "prep" ifadesi geçen talepler `dmz-preprod`
ortamına işaret eder, `preprod`'a değil.

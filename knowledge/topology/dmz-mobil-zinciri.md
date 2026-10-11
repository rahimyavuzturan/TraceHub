---
type: topology
title: "DMZ Mobil İstek Zinciri"
aliases: ["dmz mobil akış", "mobil prep zinciri", "prep mobil"]
tags: ["dmz", "mobil", "zincir"]
owner: "DevOps"
updated: 2026-09-30
confidence: high

chain:
  - layer: netscaler
    name: "vs_msube_prep_443"
    environment: dmz-preprod
    check: "vserver UP mu, kaç member DOWN durumda?"
  - layer: web
    service: msube-web
    environment: dmz-preprod
    check: "Pod'lar Running ve Ready mi, 5xx oranı arttı mı?"
  - layer: integration
    service: boa-integration
    environment: dmz-preprod
    check: "Backend çağrılarında timeout veya connection refused var mı?"
  - layer: backend
    service: boa-backend
    environment: preprod
    check: "Windows servisi çalışıyor mu, event log'da hata var mı?"
---

# DMZ Mobil İstek Zinciri

Mobil uygulamadan gelen bir istek bu dört katmandan geçer. Arıza analizinde
**sırayla** ilerleyin; sağlıklı bulduğunuz katmanı eleyip bir sonrakine geçin.

> Bu doküman bir örnektir. Gerçek ortam değerleriyle güncellenmelidir.

## Neden bu sıra?

Kullanıcı "mobilde arıza var" dediğinde ilk şüpheli çoğunlukla mobil uygulamanın
kendisi değildir. Geçmiş vakaların çoğunda sorun **backend** katmanında çıkmış,
ama belirti en üstteki katmanda görülmüştür.

## Katman notları

### NetScaler

`vs_msube_prep_443` vserver'ı arkasında birden fazla member vardır. Bir member DOWN
olsa bile trafik akmaya devam eder — bu yüzden "site açılıyor" demek sorun yok demek
değildir. Member sayısını ve her birinin durumunu ayrı ayrı kontrol edin.

### Web ve Integration

Her ikisi de `dmz-cluster` üzerindedir. Bu katmanlarda `traceId` alanı korunur,
bu yüzden bir isteği uçtan uca takip edebilirsiniz.

### Backend

Backend DMZ'de **değildir**, iç ağdaki `preprod` ortamındadır ve Windows sunucularda
çalışır. Buraya Kubernetes araçlarıyla değil, WinRM araçlarıyla bakılır.
Zincirin en sık kırıldığı ve en geç fark edilen yeri burasıdır.

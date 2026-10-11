---
type: case
title: "msube-web CrashLoopBackOff — eksik ConfigMap anahtarı"
aliases: []
tags: ["kubernetes", "mobil", "configmap"]
owner: "DevOps"
updated: 2026-09-30
confidence: high

symptom: "Pod sürekli yeniden başlıyor, önceki container log'unda KeyNotFoundException görülüyor"
environment: dmz-preprod
services: ["msube-web"]
root_cause: "ConfigMap'te BackendUrl anahtarı yoktu; deploy sırasında eklenmemiş"
resolution: "ConfigMap'e eksik anahtar eklendi, deployment yeniden başlatıldı"
detection_signals:
  - "CrashLoopBackOff"
  - "KeyNotFoundException"
  - "BackendUrl"
  - "ConfigMap"
time_to_resolve_minutes: 35
---

# msube-web CrashLoopBackOff — eksik ConfigMap anahtarı

> Bu doküman bir örnektir. Gerçek vakalar zamanla otomatik olarak birikecektir.

## Belirti

`dmz-mobile-prep` namespace'indeki `msube-web` pod'ları `CrashLoopBackOff` durumunda.
Pod hiç `Ready` olmuyor, yeniden başlatma sayacı sürekli artıyor.

## Araştırma

Çalışan container'da log yoktu çünkü container hemen kapanıyordu. Çözüm, **önceki**
container'ın loglarına bakmak oldu (`--previous`). Orada şu satır görüldü:

```
System.Collections.Generic.KeyNotFoundException: The given key 'BackendUrl' was not present
```

`describe pod` çıktısında `Last State: Terminated, Exit Code: 1` görüldü — yani
uygulama kendi kararıyla kapanmıştı, OOMKilled veya probe hatası değildi.

## Kök neden

Önceki gün yapılan bir deploy ile uygulama yeni bir ayar okumaya başlamış, ancak
ConfigMap güncellenmemişti. Uygulama açılışta bu anahtarı bulamayınca kapanıyordu.

## Çözüm

ConfigMap'e `BackendUrl` anahtarı eklendi ve deployment yeniden başlatıldı.

## Ders

**CrashLoopBackOff gördüğünüzde ilk yapılacak iş önceki container'ın loglarına bakmaktır.**
Çalışan container'ın logu boş olduğu için "log yok" sanılıp yanlış yöne gidilebilir.
Ayrıca `Exit Code` değeri kök nedeni daraltır: `1` uygulama hatası, `137` OOMKilled.

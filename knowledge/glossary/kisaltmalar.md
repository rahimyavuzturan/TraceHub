---
type: glossary
title: "Kurum Kısaltmaları ve Terimler"
aliases: ["kısaltmalar", "sözlük", "terimler"]
tags: ["sözlük"]
owner: "DevOps"
updated: 2026-09-30
confidence: high
---

# Kurum Kısaltmaları ve Terimler

Kullanıcılar talep yazarken bu terimleri kullanır. Sistem adlarıyla eşleşmeleri
bu dosyadan öğrenilir.

> Bu doküman bir örnektir. Ekipten toplanan gerçek terimlerle doldurulmalıdır.

## Uygulama kısaltmaları

**msube** — Mobil Şube. Mobil uygulamanın sunucu tarafı. Sistem adı `msube-web`.

**isube** — İnternet Şubesi. Web tarayıcıdan girilen şube uygulaması.

**tsube** — Ticari Şube. Kurumsal müşterilere yönelik şube uygulaması.

**BOA** — Kurumun ana bankacılık uygulama ailesi. Azure DevOps'ta repolar
`KT/BOA` projesi altındadır.

## Ortam terimleri

**prep** — Kullanıcılar "preprod" yerine sıklıkla "prep" der. Mobil ve DMZ
bağlamında geçtiğinde genellikle `dmz-preprod` ortamı kastedilir, `preprod` değil.

**DMZ** — Dış ağa açık, ayrı cluster'da duran ortam. İç ortamla aynı isimli
uygulamalar burada da koşar; hangisinin kastedildiği mutlaka netleştirilmelidir.

**altortam** — prod dışındaki tüm ortamların ortak adı (test, preprod).

## Süreç terimleri

**Mercek** — Kurum içi değişiklik ve talep yönetim sistemi. "Mercek'ten talep aç"
ifadesi, işlemin kayıt altına alınması gerektiği anlamına gelir.

## Kubernetes terimleri

**CrashLoopBackOff** — Pod'un sürekli başlayıp kapanması. Kubernetes yeniden
başlatmalar arasındaki süreyi kademeli artırır. Kök neden neredeyse her zaman
**önceki** container'ın loglarındadır.

**OOMKilled** — Container bellek limitini aştığı için çekirdek tarafından
sonlandırıldı. `Exit Code: 137` ile birlikte görülür.

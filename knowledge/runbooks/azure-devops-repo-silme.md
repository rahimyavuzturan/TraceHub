---
type: runbook
title: "Azure DevOps Repo Silme Prosedürü"
aliases: ["repo silme", "repository kaldırma", "depo silme"]
tags: ["azure-devops", "prosedür"]
owner: "DevOps"
updated: 2026-09-30
confidence: high

applies_to: ["azure-devops"]
approvals_required:
  - "Repo sahibi ekip yöneticisinin yazılı onayı"
  - "Mercek üzerinden açılmış değişiklik talebi"
risk: high
reversible: false
---

# Azure DevOps Repo Silme Prosedürü

Silinen bir repo kalıcı olarak kaybolur. Bu prosedür adım adım takip edilmelidir.

> Bu doküman bir örnektir. Kurumun gerçek prosedürüyle güncellenmelidir.

## Ön koşullar

Silme işlemine başlamadan önce aşağıdakilerin **hepsi** doğrulanmış olmalıdır:

1. Repo sahibi ekip belirlenmiş ve yöneticisinden yazılı onay alınmış.
2. Mercek üzerinden değişiklik talebi açılmış ve onaylanmış.
3. Repoya bağlı aktif bir pipeline olmadığı kontrol edilmiş.
4. Başka bir repodan submodule veya paket bağımlılığı olarak referans verilmediği
   kontrol edilmiş.

Bu maddelerden biri eksikse **işleme başlamayın**, talebi geri çevirin.

## Adımlar

1. Reponun son durumunu yedekleyin: `git clone --mirror` ile tam bir kopya alın
   ve arşiv paylaşımına kaldırın.
2. Azure DevOps arayüzünde **Project Settings → Repositories** yolunu izleyin.
3. İlgili repoyu bulun, sağdaki menüden **Delete** seçeneğine tıklayın.
4. Onay kutusuna repo adını yazarak işlemi doğrulayın.
5. Mercek talebini sonuç notuyla kapatın; yedek arşiv yolunu nota ekleyin.

## Doğrulama

- Repo listede görünmüyor.
- Repoya bağlı pipeline'lar "repository not found" hatası **vermiyor**
  (veriyorsa pipeline'lar temizlenmemiş demektir).

## Geri alma

**Geri alma yoktur.** Azure DevOps silinen repoyu kısa bir süre soft-delete'te
tutabilir, ancak buna güvenilmemelidir. 1. adımdaki yedek tek güvencedir.

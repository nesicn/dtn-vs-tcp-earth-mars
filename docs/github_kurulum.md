# GitHub deposunu kurma

## Nesibe (depoyu açan kişi, Windows)

1. **Git kurulu mu?** PowerShell'de `git --version`. Hata verirse
   [git-scm.com](https://git-scm.com/download/win) adresinden kur (varsayılan ayarlar yeterli).
   İlk kez kullanıyorsan kimliğini tanıt:
   ```powershell
   git config --global user.name "Nesibe ..."
   git config --global user.email "github-hesabindaki@eposta.com"
   ```
2. **Depoyu GitHub'da aç:** github.com → sağ üstte **+** → **New repository**.
   - Repository name: `dtn-mars-projesi`
   - **Private** seç.
   - README, .gitignore ve license **ekleme** (hepsi bu klasörde zaten var).
   - **Create repository**.
3. **Arkadaşlarını ekle:** depoda **Settings → Collaborators → Add people**, Elif ve
   Azra'nın GitHub kullanıcı adlarıyla. Gelen daveti e-postadan kabul etmeleri gerekir.
4. **Dosyaları yükle:** zip'i aç, klasöre gir ve PowerShell'de:
   ```powershell
   cd C:\...\dtn-mars-projesi
   git init
   git add .
   git commit -m "Trafik betikleri, deney koşturucu ve analiz"
   git branch -M main
   git remote add origin https://github.com/<kullanici-adin>/dtn-mars-projesi.git
   git push -u origin main
   ```
   İlk `push`'ta tarayıcıda GitHub girişi açılır; onaylaman yeterli.
5. GitHub'da depoyu yenile: dosyalar görünüyorsa tamam.

`.gitattributes` ilk commit'te olmalı (zip'te var). Windows'ta yazılan betiklerin Linux
konteynerlerinde bozulmadan çalışmasını sağlar.

## Elif ve Azra (Mac)

```bash
git clone https://github.com/<nesibenin-kullanici-adi>/dtn-mars-projesi.git
cd dtn-mars-projesi
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s testler -v
```

## Günlük çalışma

```bash
git pull                      # başlamadan önce
git add <dosyalar>
git commit -m "Ne yaptığını tek cümleyle yaz"
git push
```

- Herkes kendi klasöründe çalışırsa çakışma neredeyse hiç olmaz.
- `sonuclar/` klasörü depoya girmez (çok büyük olabilir). Koşu sonuçlarını zip'leyip
  grupta paylaşın; analiz için `sonuclar/` altına açmak yeterli.
- Commit geçmişi, hocanın istediği katkı beyanı için de kanıttır; anlamlı mesajlar yazın.

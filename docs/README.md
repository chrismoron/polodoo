# Landing page — polodoo.pl

Statyczna strona projektu, hostowana przez GitHub Pages z tego katalogu.

## Konfiguracja GitHub Pages

Na repo settings:

1. **Settings → Pages**
2. **Source**: Deploy from a branch
3. **Branch**: `main` · **Folder**: `/docs`
4. **Custom domain**: `polodoo.pl` (CNAME jest już w tym folderze)

## DNS dla polodoo.pl

W panelu rejestratora:

```
A    polodoo.pl         185.199.108.153
A    polodoo.pl         185.199.109.153
A    polodoo.pl         185.199.110.153
A    polodoo.pl         185.199.111.153
AAAA polodoo.pl         2606:50c0:8000::153
AAAA polodoo.pl         2606:50c0:8001::153
AAAA polodoo.pl         2606:50c0:8002::153
AAAA polodoo.pl         2606:50c0:8003::153
CNAME www.polodoo.pl    ksegit.github.io.
```

Po propagacji DNS (~kilka minut do kilku godzin) i włączeniu "Enforce HTTPS"
w GitHub Pages, strona będzie dostępna pod https://polodoo.pl.

## Lokalna iteracja

```bash
# Podejrzyj w przeglądarce
open docs/index.html

# Albo prosty serwer
python3 -m http.server -d docs 8000
# → http://localhost:8000
```

## Co edytować

Pojedynczy plik `index.html` zawiera całą stronę (HTML + CSS inline). Zero
buildu, zero dependency. Aktualizuj sekcje:

- **`<section id="features">`** — siatka funkcji
- **`<section id="compliance">`** — tabela kalendarium
- **`<section id="pricing">`** — Community vs Pro
- **`<footer>`** — linki

Dodanie nowej sekcji: skopiuj `<section>` z innego miejsca, zmień ID i treść.

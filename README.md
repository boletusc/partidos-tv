# Partidos TV

Web-app personal (PWA) con los partidos del día y sus canales por idioma, a partir de futbolenlatv.es y sus webs hermanas.

- `scraper.py`: descarga las webs y genera `site/data.json` (lo ejecuta GitHub Actions cada 30 min).
- `site/`: la app (HTML/CSS/JS sin dependencias), publicada en GitHub Pages.
- `make_icons.py`: regenera los iconos.

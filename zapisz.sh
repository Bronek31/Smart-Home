#!/bin/sh
# Pobranie odczytów i zapisanie ich do repozytorium, odporne na wyścig dwóch przebiegów.
#
# Kolektor rusza z dwóch źródeł: co godzinę z harmonogramu i przy każdym pushu na main.
# Grupa concurrency ma je szeregować, ale 15.08 dwa przebiegi powstały w odstępie czterech
# sekund i obie kopie ruszyły równolegle. Przegrany dostał odmowę pusha i próbował
# `pull --rebase` — a że oba przebiegi przepisują te same pliki (index.json i pogoda.json
# mają w środku własny znacznik czasu), rebase stanął na konflikcie i przebieg padł.
#
# Rebase był tu złym narzędziem. Pliki w data/ nie są ręczną pracą, którą trzeba pogodzić,
# tylko wynikiem, który umiemy policzyć jeszcze raz. Przy odmowie pusha bierzemy więc stan
# zwycięzcy i liczymy od nowa na jego drzewie: fetch.py dokłada swoje okno do tego, co
# zastanie na dysku, więc wynik jest sumą obu przebiegów, a konflikt nie ma jak powstać.
#
# Zmienne (ustawiane w testach, w Actions zostają domyślne):
#   KOMENDA_POBIERZ  czym pobrać odczyty
#   GALAZ            dokąd pisać
#   PROBY            ile razy powtórzyć przy przegranym wyścigu
set -e

KOMENDA_POBIERZ=${KOMENDA_POBIERZ:-"python fetch.py --days 7"}
GALAZ=${GALAZ:-main}
PROBY=${PROBY:-3}

git config user.name  "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

proba=1
while [ "$proba" -le "$PROBY" ]; do
  sh -c "$KOMENDA_POBIERZ"

  git add data/
  if git diff --staged --quiet; then
    echo "Brak nowych odczytów — nic do zapisania."
    exit 0
  fi

  git commit -q -m "odczyty: $(date -u '+%Y-%m-%d %H:%M') UTC"
  if git push -q origin "HEAD:$GALAZ"; then
    echo "Odczyty zapisane."
    exit 0
  fi

  # Ktoś wyprzedził nas na gałęzi. Nie godzimy dwóch wersji tych samych plików —
  # zaczynamy od jego stanu i liczymy jeszcze raz.
  echo "Push odrzucony (próba $proba) — ktoś zapisał w międzyczasie, liczę od jego stanu."
  git fetch -q origin "$GALAZ"
  git reset -q --hard "origin/$GALAZ"
  proba=$((proba + 1))
done

echo "Nie udało się zapisać odczytów po $PROBY próbach." >&2
exit 1

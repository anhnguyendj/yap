#!/usr/bin/env bash
# Quet key truoc khi push.
# LUAT: chi in TEN FILE va SO LUONG. Khong bao gio in gia tri key ra man hinh.
cd "$(dirname "$0")"

# Key that: gsk_ + >=40 ky tu. Placeholder kieu gsk_xxxx bi loai o buoc sau.
PAT='gsk_[A-Za-z0-9]{40,}|sk-[A-Za-z0-9]{40,}|ghp_[A-Za-z0-9]{36,}|xox[baprs]-[A-Za-z0-9-]{20,}'

in_repo=0
git rev-parse --git-dir >/dev/null 2>&1 && in_repo=1
[ $in_repo -eq 0 ] && echo "  (chua phai repo git - chi bao file nao co key)"

bad=0
while IFS= read -r f; do
  n=$(grep -oE "$PAT" "$f" 2>/dev/null | grep -vE '[xX]{8,}' | wc -l)
  [ "$n" -gt 0 ] || continue
  if [ $in_repo -eq 1 ] && git check-ignore -q -- "$f" 2>/dev/null; then
    echo "  OK  $f  ($n key) - da bi .gitignore chan"
  elif [ $in_repo -eq 1 ] && ! git ls-files --error-unmatch -- "$f" >/dev/null 2>&1; then
    echo "  !!  $f  ($n key) - CHUA bi chan, chua duoc theo doi. Them vao .gitignore."
    bad=1
  else
    echo "  !!  $f  ($n key) - SE BI PUSH LEN. Dung lai."
    bad=1
  fi
done < <(find . -type f ! -path "./.git/*" ! -name "*.ico" ! -name "*.png")

if [ $bad -eq 0 ]; then
  echo ">> SACH. Push duoc."
else
  echo ">> DUNG LAI. Revoke key, sua .gitignore, roi quet lai."
  exit 1
fi

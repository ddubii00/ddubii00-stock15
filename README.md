# Telegram Reader

내 Telegram 계정의 채널·그룹·개인대화를 한 화면에서 읽는 개인용 웹앱입니다. React + Vite + TypeScript, Python 3 + FastAPI + Telethon stable 1.x, SQLite로 구성합니다. Oracle Ubuntu에서 nginx의 HTTPS `/stock15-7/` 경로로 운영합니다.

메시지 보내기·수정·삭제·전달·읽음 처리·채널 가입/탈퇴 기능은 없습니다. X는 이 앱에서 숨기는 동작이며 Telegram 원본은 변경하지 않습니다. OpenAI API, AI 요약, 유료 DB, Redis, analytics는 사용하지 않습니다.

## 주요 화면

- 대화방 선택 drawer: 검색, 채널·그룹·개인대화 필터, 전체 선택/해제.
- 오늘 KST 날짜 기본 조회, 날짜 picker, 더 보기. `시간순`은 최신 메시지부터 표시하고, `대화방순`은 대화방 이름순으로 묶어 각 방 안에서는 최신 메시지부터 표시합니다. 정렬 전환은 추가 Telegram 조회 없이 즉시 적용됩니다.
- `선택한 대화방`을 클릭하면 해당 방만 표시합니다. 다른 방을 클릭하면 함께 표시하고, 같은 방을 다시 클릭하면 표시에서 제외합니다. 마지막 방을 해제하면 빈 피드가 되고 `전체 피드`를 누르면 등록된 방을 모두 표시합니다. 표시 필터는 현재 화면에만 적용되며 서버의 대화방 등록 목록은 유지합니다.
- X는 클릭 즉시 메시지를 화면에서 숨기고 ID 저장을 뒤에서 처리합니다. 저장 실패 시 메시지를 복원하고 오류를 표시합니다. 저장 성공 시 전체 피드를 다시 조회하지 않으며, 진행 중이던 조회 응답에도 숨김을 적용합니다. 다른 기기의 변경은 기존 15초 확인/창 포커스 동기화를 유지합니다.
- `밝음`/`어두움` 버튼으로 배경, 메시지 카드, 사이드바, 설정창의 색을 전환합니다. 테마는 Oracle의 최소 설정 DB에 저장되어 다음 로그인과 다른 컴퓨터에도 적용됩니다. 표시 필터는 브라우저 저장소에 기록하지 않습니다.
- 웹앱 비밀번호 로그인, 서버 쿠키, CSRF, 로그인 시도 제한.
- SQLite의 선택·숨김·조회 시작일·테마를 모든 기기가 공유합니다. 로그인과 창 포커스 시에만 메타데이터를 확인하며, 피드에 영향을 주는 변경에만 다시 조회합니다.
- Telegram 메시지는 최초 표시와 사용자가 오늘 화면의 `새로고침`을 누를 때만 조회합니다. 반복 자동 조회는 하지 않으므로 Telegram 요청 제한을 줄입니다.
- 링크가 있으면 Telegram의 미리보기 제목·설명을 우선 표시하고, 외부 페이지의 공개 대표 이미지·설명으로 보충합니다. 설명이 없으면 공개 페이지 첫 문단의 짧은 부분을 사용합니다. YouTube는 썸네일과 영상 설명 일부를 보여 주고 누르면 영상 원문을 새 창으로 엽니다. YouTube 페이지는 설명 태그가 뒤에 있어 최대 1MiB의 HTML만 메모리에서 읽습니다. Oracle에는 링크 원문·이미지·동영상·미리보기 데이터를 파일, SQLite, 캐시로 저장하지 않고 요청 순간의 HTML 응답만 메모리에서 읽어 즉시 버립니다. 외부 사이트가 미리보기를 차단하면 가능한 정보와 기존 링크만 표시합니다.
- Telemoa 인기 종목 6개와 핵심 블로그 6개를 표시합니다. 최신/누적 전환, 언급/스크랩 수, 원문 링크, 출처와 조회시간을 표시합니다. 목록은 60초 메모리 캐시만 사용하며 원문 블로그 전문을 복제하지 않습니다. 이 영역은 선택한 개인 Telegram 대화와 별도이며 Telegram 비밀정보를 Telemoa에 보내지 않습니다. Telemoa 공개 API 형식이 바뀌거나 접근이 제한되면 오류와 원문 링크를 표시합니다.
- `기록삭제`: 확인창 후 선택 대화방, 숨김 ID, 설정, 모든 웹 로그인 세션을 삭제하고 SQLite의 빈 페이지를 정리합니다. 조회 시작일은 오늘로 돌아갑니다. Telegram 인증 session과 `/etc/stock15-7.env`는 유지합니다. 소스, Telegram 원본, 별도의 백업은 삭제하지 않습니다.

## 보안과 저장 정책

**Telegram session 파일을 획득한 사람은 Telegram 계정에 접근할 수 있으므로 API hash나 비밀번호와 동일하거나 그 이상으로 보호해야 한다.**

- 실제 secret은 사용자가 Oracle에서 직접 입력합니다. 코드, fixture, README, Git history에 실제 값을 넣지 않습니다. `.env.example`에는 값 없이 변수 이름만 있습니다.
- Telegram 인증 session: `/var/lib/stock15-7/session/telegram.session`, 전용 사용자 소유, `600`. 디렉터리 `700`.
- 환경변수: `/etc/stock15-7.env`, root 소유 `600`. systemd가 읽어 전용 사용자 프로세스에 전달합니다.
- 설정 DB: `/var/lib/stock15-7/app.sqlite3`, 전용 사용자 소유 `600`.
- 웹 쿠키: HttpOnly, Secure, SameSite=Strict, 경로 `/stock15-7/`, 유효기간 12시간. 비밀번호나 메시지를 localStorage/IndexedDB에 저장하지 않습니다. 비밀번호는 로그인 요청 중에만 메모리에 있으며 즉시 입력칸을 비웁니다.
- 로그인 Origin 검사와 변경 요청의 Origin + CSRF 검사를 합니다. `APP_ORIGIN`은 HTTPS origin이고 끝에 경로를 붙이지 않습니다. 비밀번호는 최소 4자이며 설정되지 않으면 서버 시작을 거부합니다.
- APP_PASSWORD는 메모리에서 scrypt 검증합니다. 웹 세션 토큰 원문은 DB에 넣지 않고 SHA-256 해시만 저장합니다. 서비스 재시작/비밀번호 변경은 모든 웹 로그인을 무효화합니다. 프로세스는 **1 worker**만 실행합니다.
- 메시지 본문/작성자/캡션/첨부 파일은 SQLite, 파일, 브라우저 저장소, analytics에 저장하지 않습니다. 실제 사진·동영상·PDF가 있을 때만 각각 표시합니다. 사진은 카드 안에서 바로 미리보고, 동영상은 카드 안의 재생 버튼으로 시청하며 중복된 동영상 버튼은 표시하지 않습니다. PDF만 별도 버튼으로 새 창에서 엽니다. 브라우저 재생기에 필요한 byte range도 Telegram에서 바로 스트리밍하며 Oracle에는 임시·영구 파일을 만들지 않습니다.
- 본문에 있는 외부 링크는 새 창으로 엽니다. 메시지 카드의 어느 부분이든 더블클릭하면 X 버튼과 같은 숨김 동작을 실행합니다.
- Telethon entity 디스크 저장을 끄고, 조회에 필요한 input peer/access_hash는 대화방 조회 결과에서 메모리로만 보관합니다. Telethon 인증 session은 메시지 DB가 아닙니다.
- 모든 응답 `Cache-Control: no-store`. nginx 캐시, 요청/응답 임시파일 buffering, access log를 끕니다. Telethon 계정 정보가 포함될 수 있는 로그를 비활성화합니다. API body debug log를 남기지 않습니다.
- 일반 소스 백업에 `/etc/stock15-7.env`, `/var/lib/stock15-7`, Telegram session을 포함하지 마세요. 앱의 기록삭제는 별도 백업/OS snapshot까지 지우지 않습니다. OS swap/core dump로 메모리가 디스크에 기록되지 않게 Oracle의 swap 정책도 확인하세요. systemd의 core dump 제한은 0입니다.

## 구조

```text
HTTPS browser /stock15-7/
  → nginx (cache/buffering 없음)
    ├─ /stock15-7/assets/ → /var/www/stock15-7/frontend/dist/assets/ 직접 제공
    └─ HTML / favicon / API → FastAPI 127.0.0.1:8017, root_path=/stock15-7
        ├─ React index.html / favicon 제공
        ├─ 서버 웹 세션 + CSRF
        ├─ Telethon → Telegram MTProto history 조회
        ├─ httpx → Telemoa 공개 목록 조회
        └─ SQLite → 선택 ID / 숨김 ID / 설정 / 웹 로그인 세션
```

`backend/app/telegram.py`는 비대화형 session 재사용과 read-only 조회, `feed.py`는 날짜 필터와 cursor merge, `db.py`는 최소 메타데이터, `auth.py`는 웹 로그인, `telemoa.py`는 공개 목록 변환을 담당합니다.

## A. 최초 Oracle 설치

전제: Python **3.11 이상**(Ubuntu 24.04의 기본 Python 사용 가능), Node.js **22.12 이상**, npm, git, nginx와 기존 HTTPS 도메인. 서버의 기존 사이트 설정은 유지하고 location 블록만 추가합니다. 이미 정상 운영 중인 서버는 아래 **B. 기존 Oracle 서버 업데이트** 절차를 사용하세요. 이 문서의 설치 명령은 Oracle에서 사용자가 실행합니다.

소스는 `/var/www/stock15-7`, venv는 그 아래 `.venv`, 서비스는 `webapp-stock15-7.service`, 환경파일은 `/etc/stock15-7.env`, 운영 데이터는 `/var/lib/stock15-7`입니다. 전용 Linux 사용자는 `telegram-reader`를 유지합니다.

### 1. Oracle에 clone

소스 저장소: [ddubii00/ddubii00-stock15](https://github.com/ddubii00/ddubii00-stock15).

```bash
sudo apt update
sudo apt install -y python3-venv git nginx
python3 --version
node --version
sudo useradd --system --user-group --home-dir /var/lib/stock15-7 --shell /usr/sbin/nologin telegram-reader
sudo install -d -m 755 -o "$USER" -g "$(id -gn)" /var/www/stock15-7
git clone https://github.com/ddubii00/ddubii00-stock15.git /var/www/stock15-7
cd /var/www/stock15-7
```

사용자가 이미 전용 사용자를 만들었다면 useradd는 생략합니다. 제공된 소스 압축파일을 Oracle의 `/var/www/stock15-7`에 풀어 같은 단계로 진행할 수도 있습니다.

### 2. Python venv 생성

```bash
umask 022
python3 -m venv .venv
```

### 3. requirements 설치

```bash
.venv/bin/pip install -r requirements.txt
```

### 4. frontend npm 설치/build

```bash
cd frontend
npm ci
npm run build
cd ..

find frontend/dist -type d -exec chmod 755 {} \;
find frontend/dist -type f -exec chmod 644 {} \;
chmod 755 \
  /var/www/stock15-7 \
  /var/www/stock15-7/frontend \
  /var/www/stock15-7/frontend/dist
```

Vite base 기본값은 `/stock15-7/`, Python APP_BASE_PATH 기본값은 `/stock15-7`입니다. 변경할 때 두 설정과 nginx location을 함께 바꿉니다. 모든 frontend API 요청은 공통 `apiUrl()` helper를 사용합니다.

서비스의 `UMask=0077`은 인증 session과 SQLite 같은 비밀·운영 파일용입니다. 공개 JS/CSS/HTML은 `telegram-reader`와 nginx의 `www-data`가 읽어야 하므로 build 후 디렉터리는 `755`, 파일은 `644`로 맞춥니다. `umask 077`로 build한 `index.html`이 `600`이면 HTML 응답 전송 오류(`Too little data for declared Content-Length`)와 JS/CSS 접근 오류가 발생할 수 있습니다. 위 chmod는 `frontend/dist`와 공개 소스 경로에만 적용하며 환경파일·session·DB에는 적용하지 않습니다.

### 5. `/etc/stock15-7.env` 사용자가 직접 생성

```bash
if ! sudo test -e /etc/stock15-7.env; then
  sudo install -m 600 -o root -g root /dev/null /etc/stock15-7.env
fi
sudo nano /etc/stock15-7.env
```

아래 변수 이름을 입력합니다. 비밀값은 문서에 쓰지 않습니다.

```text
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=
APP_PASSWORD=
TELEGRAM_SESSION_PATH=
APP_DB_PATH=
APP_ORIGIN=
APP_BASE_PATH=
TZ=
```

### 6. 실제 Telegram API ID/hash/전화번호 입력

[my.telegram.org](https://my.telegram.org)에서 API ID와 API HASH를 직접 발급받아 위 파일에서만 입력합니다. TELEGRAM_PHONE은 국가코드를 포함합니다. APP_PASSWORD도 같은 파일에서 직접 정합니다. 2FA 비밀번호/인증코드는 파일에 넣지 않습니다.

비밀이 아닌 값은 다음과 같이 설정합니다.

- TELEGRAM_SESSION_PATH: `/var/lib/stock15-7/session/telegram.session`
- APP_DB_PATH: `/var/lib/stock15-7/app.sqlite3`
- APP_ORIGIN: 실제 `https://도메인` (끝의 `/`와 `/stock15-7/` 제외)
- APP_BASE_PATH: `/stock15-7`
- TZ: `Asia/Seoul`

```bash
sudo chown root:root /etc/stock15-7.env
sudo chmod 600 /etc/stock15-7.env
```

### 7. `scripts/telegram_login.py` 실행

먼저 session 디렉터리를 만듭니다. 초기 인증 중에는 웹 서비스를 실행하지 않습니다. 파일을 읽는 root 권한과 session을 생성하는 전용 사용자를 분리하기 위해 `systemd-run`을 사용합니다.

```bash
sudo install -d -m 700 -o telegram-reader -g telegram-reader /var/lib/stock15-7/session
sudo systemd-run --collect --wait --pty \
  --uid=telegram-reader --gid=telegram-reader \
  --working-directory=/var/www/stock15-7 \
  --property=EnvironmentFile=/etc/stock15-7.env \
  --property=UMask=0077 \
  /var/www/stock15-7/.venv/bin/python scripts/telegram_login.py
```

전용 사용자로 환경변수가 안전하게 주입된 터미널이라면 다음 명령도 동일합니다.

```bash
python scripts/telegram_login.py
```

### 8. Telegram 인증코드 입력

Telegram이 전달한 코드를 터미널 프롬프트에서 직접 입력합니다. 인증코드도 getpass로 화면에 표시하지 않습니다. 브라우저에서는 Telegram 인증을 진행하지 않습니다.

### 9. 2FA가 있으면 password 입력

getpass 프롬프트에서 직접 입력합니다. 화면, 파일, 로그에 저장하지 않습니다.

### 10. session 생성 확인

```bash
sudo stat -c '%a %U %G %n' /var/lib/stock15-7/session/telegram.session
```

session 내용을 cat하거나 공유하지 마세요.

### 11. session chmod 600

```bash
sudo chown telegram-reader:telegram-reader /var/lib/stock15-7/session/telegram.session
sudo chmod 600 /var/lib/stock15-7/session/telegram.session
```

### 12. DB directory 생성

```bash
sudo install -d -m 700 -o telegram-reader -g telegram-reader /var/lib/stock15-7
```

앱이 `app.sqlite3`과 정확히 네 개의 테이블을 자동 생성합니다. 소스 디렉터리와 venv/build는 전용 사용자가 읽을 수 있어야 하지만 수정 권한은 필요 없습니다.

### 13. systemd 시작

```bash
sudo install -m 644 deploy/webapp-stock15-7.service /etc/systemd/system/webapp-stock15-7.service
sudo systemctl daemon-reload
sudo systemctl enable --now webapp-stock15-7.service
sudo systemctl status webapp-stock15-7.service --no-pager
```

의도적으로 단일 worker입니다. session 파일 하나를 여러 프로세스가 동시에 열지 않습니다.

### 14. nginx 설정

`deploy/nginx-telegram-reader.conf` 내용을 기존 **HTTPS server 블록 내부**에 추가합니다. APP_ORIGIN과 해당 도메인이 일치해야 합니다. Secure cookie 때문에 HTTPS가 필요합니다. 인증서/실제 도메인 값은 사용자가 서버에서 설정합니다.

필수 구조는 아래 두 location입니다. `location ^~ /stock15-7/assets/`의 `^~` 및 `alias /var/www/stock15-7/frontend/dist/assets/;`의 끝 `/`를 유지하세요. 다른 nginx 정규식 location보다 assets location을 우선하고, Vite JS/CSS는 FastAPI로 넘기지 않습니다. HTML이 200이어도 assets가 404이면 백지 화면이 됩니다.

```nginx
location ^~ /stock15-7/assets/ {
    alias /var/www/stock15-7/frontend/dist/assets/;
    access_log off;
    add_header Cache-Control "no-store" always;
}

location /stock15-7/ {
    proxy_pass http://127.0.0.1:8017/;
    # 나머지 proxy/header/no-buffer 설정은 deploy/nginx-telegram-reader.conf 사용
}
```

```bash
sudo nano /etc/nginx/sites-available/현재사이트설정파일
sudo nginx -t
sudo systemctl reload nginx
```

FastAPI는 127.0.0.1:8017에서만 대기합니다. Oracle/Ubuntu 방화벽에서 8017을 외부에 열지 않습니다. `/stock15-7`은 `/stock15-7/`로 redirect됩니다. `proxy_pass http://127.0.0.1:8017/;`의 마지막 slash를 유지하세요.

### 15. 브라우저 접속

최종 주소: **`https://실제-Oracle-도메인/stock15-7/`**

웹앱 비밀번호로 로그인 → 대화방 선택 → 적용. 기본 조회 시작일은 첫 실행의 오늘 KST 날짜이며 설정에서 이전 날짜로 바꿀 수 있습니다. 운영 접속 주소는 서버에 설정한 APP_ORIGIN 뒤에 `/stock15-7/`를 붙인 주소입니다.

## B. 기존 Oracle 서버 업데이트

현재 정상 운영 중인 `/var/www/stock15-7` 저장소에서 실행합니다. `git reset --hard origin/main`은 이 저장소의 추적된 소스 변경을 버리고 GitHub 버전으로 맞춥니다. 필요한 미커밋 소스 변경이 있으면 먼저 별도로 보관하세요.

```bash
cd /var/www/stock15-7

git fetch origin
git reset --hard origin/main

.venv/bin/pip install -r requirements.txt

cd frontend
npm ci
npm run build
cd ..

find frontend/dist -type d -exec chmod 755 {} \;
find frontend/dist -type f -exec chmod 644 {} \;
chmod 755 \
  /var/www/stock15-7 \
  /var/www/stock15-7/frontend \
  /var/www/stock15-7/frontend/dist

.venv/bin/python scripts/deployment_check.py
.venv/bin/python scripts/security_check.py

sudo systemctl restart webapp-stock15-7.service
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl status webapp-stock15-7.service --no-pager
```

업데이트 명령에는 env 생성, Telegram 재인증, DB 초기화, service 파일 설치, nginx 파일 복사가 없습니다. `/etc/systemd/system/webapp-stock15-7.service`와 현재 nginx `all-stocks` 설정은 덮어쓰지 않습니다. **GitHub 소스 업데이트와 운영 systemd/nginx 설정 업데이트는 별도 작업**입니다. 템플릿 변경을 실제 `/etc`에 반영해야 할 경우에만 기존 설정과 비교해 별도로 적용합니다.

`git reset --hard origin/main`은 `/var/www/stock15-7`의 Git working tree를 변경하며, 저장소 밖의 아래 파일에는 영향을 주지 않습니다.

```text
/etc/stock15-7.env
/var/lib/stock15-7/session/telegram.session
/var/lib/stock15-7/app.sqlite3
```

따라서 Telegram API ID/HASH·전화번호·웹앱 비밀번호와 Telegram 인증 session, 선택한 대화방, 숨김 메시지 ID, 조회 시작일 등 SQLite 설정은 유지됩니다. 서비스가 재시작되면 앱 설계상 **웹 브라우저 로그인 session은 초기화**되므로 웹앱 비밀번호를 다시 입력해야 합니다. Telegram 인증 session은 유지되어 재인증할 필요가 없습니다.

업데이트 후 브라우저에서 HTML과 개발자도구 Network의 `/stock15-7/assets/*.js`·`*.css`가 모두 200인지 확인합니다. assets 404 또는 파일 읽기 오류는 nginx alias와 위 공개 파일 권한부터 확인하세요. 이 소스 작업은 Oracle 서버의 실제 설정 파일을 수정하지 않습니다.

## SQLite schema

```sql
CREATE TABLE selected_chats (
    chat_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE hidden_messages (
    chat_id TEXT NOT NULL,
    message_id INTEGER NOT NULL CHECK(message_id > 0),
    hidden_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, message_id)
);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE web_sessions (
    token_hash TEXT PRIMARY KEY,
    csrf_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
```

app_settings에는 history_start_date, theme, 변경 감지용 state_revision만 저장합니다. 선택/숨김/설정 변경마다 revision이 증가합니다. 숨김 필터는 `(chat_id, message_id)` batch SQL로 조회합니다. DB 크기는 숨긴 ID 개수에 따라 증가하며 본문 크기와는 무관합니다. 만료 세션은 로그인 때 정리합니다.

## Telegram API, 날짜, pagination

CLI에서만 send_code_request/sign_in 인증을 합니다. 웹 서버는 connect/is_user_authorized, iter_dialogs, iter_messages로 기존 session의 history만 읽고, 사용자가 첨부 링크를 누를 때만 iter_download로 바이트를 HTTP 응답에 스트리밍합니다. 이 과정은 저장 파일을 만들지 않습니다. `receive_updates=False`, `save_entities=False`, `flood_sleep_threshold=0`, 유한 재시도와 4개의 semaphore로 제한합니다. FloodWait는 HTTP 429 + Retry-After로 전달하고 무한 재시도하지 않습니다. 여러 브라우저의 피드 요청도 순차 처리합니다.

날짜는 ZoneInfo('Asia/Seoul')로 계산한 `[당일 00:00, 다음 날 00:00)` 반개구간을 UTC로 변환합니다. 모든 Telegram timestamp는 timezone-aware여야 합니다. 2026-10-02 15:01 UTC와 2026-10-03 14:59 UTC는 모두 2026-10-03 KST에 포함되고, 다음 날 00:00은 제외됩니다.

피드 cursor는 각 방의 마지막 소비 ID, 완료 여부, 날짜/정렬/선택/시작일과 유효기간만 담고 HMAC으로 서명합니다. 메시지 본문은 cursor에도 넣지 않습니다. 1회 응답 최대 100개, 방당 raw 조회 최대 101개, 선택 대화방 최대 200개입니다. 전역 정렬을 유지하기 위해 모든 방의 조회 경계가 확보된 메시지만 합쳐 전달합니다. 숨긴 메시지가 빽빽한 구간은 빈 페이지+더 보기가 나올 수 있으나 cursor가 전진하고 메시지를 건너뛰지 않습니다. cursor는 1시간 또는 프로세스 재시작 시 만료됩니다. Telegram 원문이 조회 도중 바뀌면 새로 조회하세요.

## API

외부에서는 모든 경로 앞에 `/stock15-7`을 붙입니다.

```text
POST   /api/auth/login
GET    /api/auth/session
POST   /api/auth/logout
GET    /api/status
GET    /api/chats
GET    /api/messages?date=2026-10-03&order=desc&limit=50
GET    /api/settings
PUT    /api/settings/chats
PUT    /api/settings/start-date
GET    /api/messages/hidden?offset=0
POST   /api/messages/hide
DELETE /api/messages/hide/{chat_id}/{message_id}
DELETE /api/messages/hide-all
DELETE /api/settings/records
GET    /api/insights/telemoa?mode=latest
```

로그인만 비인증 접근이 가능합니다. 나머지 API는 모두 인증이 필요합니다. 변경 요청은 동일 Origin과 X-CSRF-Token이 필요합니다. 정적 GUI 자산에는 비밀정보가 없으며 공개됩니다.

## 로컬 미리보기와 테스트

예시 Telegram 데이터만 사용하는 개발 전용 미리보기입니다. demo 코드는 production build에서 제거됩니다. Telemoa는 실제 공개 데이터를 읽습니다.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/preview_external.py
```

별도 터미널:

```bash
cd frontend
npm ci
npm run dev
```

접속: `http://127.0.0.1:5173/stock15-7/?demo=1`. 로컬 공개 데이터 preview 서버는 127.0.0.1:8015이며 운영 systemd에서는 실행하지 않습니다. 실제 Telegram 사용 환경은 HTTPS의 production build를 이용하세요.

```bash
cd frontend
npm run build
npm test
cd ..
.venv/bin/python -m pytest
.venv/bin/python scripts/deployment_check.py
.venv/bin/python scripts/security_check.py
```

테스트는 runtime에서 임의의 테스트 비밀번호를 만들며 실제 credential을 fixture에 넣지 않습니다. 인증 차단, cookie/CSRF, Telegram 상태, dialog 변환, 기기별 선택/숨김 동기화, UTC/KST 경계, 시작일, 숨김 밀집 pagination의 정렬·중복·누락, DB schema와 실제 파일에 본문 부재, no-store, subpath, gitignore, 기록삭제 후 전체 세션 무효화를 검증합니다. 실제 개인 Telegram 계정/Oracle 운영 연결 검증은 사용자 인증과 서버 설치 후 수행합니다.

`deployment_check.py`는 프런트 경로·백엔드 기본값/4자 검증·systemd 이름/경로/권한·nginx assets alias/8017 proxy 및 문서의 업데이트 보존 규칙이 일치하는지 검사합니다. CI에서도 같은 검사를 실행합니다. Oracle의 실제 nginx/systemd 설정을 읽거나 변경하는 스크립트가 아니며, 실제 설정 문법은 Oracle의 `nginx -t`로 확인합니다.

## GitHub 소스 관리

소스 저장소는 `ddubii00/ddubii00-stock15`입니다. `.env`, `.env.*`(빈 `.env.example` 제외), session과 journal, sqlite 및 sidecar, data, secrets, 로그, private key는 gitignore합니다. 이후 변경사항도 아래 검사를 거친 뒤 commit/push하세요. Oracle 운영 데이터와 인증정보는 서버에서 별도로 관리합니다.

```bash
git status --short
git ls-files
python scripts/security_check.py
```

보안 용어/변수명의 존재는 정상입니다. 실제 값, 계정 인증 파일, 메시지 DB가 추적되지 않는지 검사해야 합니다. 소스 압축파일도 Git 추적 대상으로 승인된 소스만 포함합니다.

공식 참고: [Telethon client](https://docs.telethon.dev/en/stable/modules/client.html), [Telethon session](https://docs.telethon.dev/en/stable/concepts/sessions.html), [FastAPI proxy/root_path](https://fastapi.tiangolo.com/advanced/behind-a-proxy/), [Telemoa](https://telemoa.com/).

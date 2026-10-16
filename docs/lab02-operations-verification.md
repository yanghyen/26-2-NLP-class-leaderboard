# Lab02 GPU 할당 전 운영 검증 — 2026-10-16

## 결과와 검증 범위

시작 시 Git 작업 트리는 깨끗했다. 저장소 루트/상위 경로에 적용되는 AGENTS.md는 없었고,
`frontend/AGENTS.md`와 현재 README·운영·보안·evaluator 문서를 확인했다.
프런트엔드 소스는 변경하지 않았다. 운영 DB/Task/점수, 원본 Notebook/ZIP은 수정하지 않았다.

| 항목 | 결과 | 근거/제한 |
|---|---|---|
| Docker 설치·기동 | 실행 불가 | `docker` 명령과 Docker Desktop 없음. `.env`도 없음 |
| Compose | 정적 확인 | PostgreSQL 16, Redis 7, API/Worker 공유 named volume, 기존 non-root/read-only/cap-drop/no-new-privileges 유지. `compose config/build/up`는 미검증 |
| PostgreSQL·Redis | 확인 완료 | 별도 `/private/tmp/lab02-ops-pg`, PostgreSQL 14 로컬 서버, Redis 7.4.2 소스 빌드. Compose의 PG16과 같은 환경이라는 주장은 아님 |
| DB migration | 확인 완료 | 새 테스트 PG DB에 0001→0005 전부 적용 |
| 실제 CPU 흐름 | 확인 완료 | 실제 HTTP multipart→기존 보안 검증→실제 Redis→실제 Worker→production Lab02 subprocess/BERT 추론→PG Score 저장 |
| 집계·리더보드·삭제 | 확인 완료 | 첫 Baseline 고정, Development 대표점수, improvement=0, 리더보드 1행, 성공 Notebook/ZIP/extracted artifact 삭제, scratch 비움 |
| 실패 안내·개인정보·권한·CSV | API 확인 완료 | 잘못된 ZIP 400, 공개 응답 학번/이름/내부 경로 미노출, 익명 관리자·CSV·artifact 접근 거부, 관리자 CSV 200, 삭제된 성공 artifact 다운로드 409 |
| Worker 중단·재시작 | 확인 완료 | 기존 코드 SIGKILL→재시작 후 RUNNING/빈 Redis 재현. 수정 코드가 같은 Job을 attempts=2에서 완료. Score 1건, 중복 dispatch 무시 |
| 학생·관리자 브라우저 | 미검증 | 접근 시 권한 거부 이후 중단했고, 사용자 후속 요청에 따라 더 진행하지 않음. 아래 사용자 체크리스트 참조 |
| GPU·전체 IMDb·운영 Docker | 미검증 | 이번 검증 범위 밖 |

테스트 서비스는 loopback만 사용했다: PostgreSQL `55439`, Redis `56379`, API `58000`, UI `3300`.
테스트 DB `lab02ops`, Task/Queue `lab02-ops-only`, 합성 수강생만 사용했다.
학습/추론에 Notebook을 실행하지 않았다. 테스트에서 기존 development scanner 설정을 사용했으며,
실제 malware scanner 검증은 아니다. 구조·ZIP·safetensors·권한 검사를 우회하거나 완화하지 않았다.

네 리뷰(공개 IMDb test 인덱스 0, 1, 12500, 12501)의 별도 smoke identity를 사용했다.
Baseline과 Development에 같은 모델 사본을 사용해 Macro F1 **0.7333333333333334**,
Accuracy **0.75**, improvement **0**을 확인했다. 전체 IMDb 성능 지표로 사용하면 안 된다.
Baseline UUID `f079da24-b87f-4e05-a8b9-e5f5c462e79b`,
Development UUID `4648a0be-403d-45d4-8f22-662d5e9607fc`는 테스트 DB에만 있다.
결과/CSV/테스트 사본은 `/private/tmp/lab02-ops/`에 보관했다. 운영 자료가 아니며 /tmp 보존은 보장되지 않는다.

자동 검증: Backend **180 passed**, Frontend **35 passed**.
마지막 관리자 수동 복구 변경 후 관련 Backend **12 passed**도 확인했다.
별도 테스트 Mock Task에서 실제 PostgreSQL의 두 동시 소비자가 같은 Job을 선점하도록 실행해
attempts=1·Score 1건을 확인했다. 이 추가 시험은 CPU 모델 품질 시험과 구분한다.
Compose YAML 파싱과 기존 보안 옵션 유지 확인은 통과했으며 Docker 실행 검증은 아니다.
CPU subprocess 테스트는 macOS 샌드박스에서 OpenMP 공유 메모리 오류가 발생해 승인된
샌드박스 밖 실행으로 통과했다. 앱의 보안 설정 변경으로 해결하지 않았다.

## 수정한 문제와 복구 동작

- Redis BLPOP 직후 또는 평가 중 프로세스가 죽으면 UUID가 Queue에서 사라지고
  DB Job이 QUEUED/RUNNING/SCORING에 남던 문제를 수정했다.
- Worker 시작 및 Job 사이 30초 주기 sweep에서 DB의 QUEUED Job을 다시 dispatch한다.
  Redis enqueue는 Lua LPOS/RPUSH로 원자적으로 중복을 방지하며 기존 FIFO 순서를 유지한다(Redis 6 이상).
- RUNNING/SCORING은 `locked_at + Task.timeout_seconds + 30초` 이후에만 회수한다.
  실행 중인 다른 Worker의 정상 Job을 재시작만으로 빼앗지 않는다. 기본 max_attempts=2이므로
  자동 재시도는 한 번이다. 소진하면 안전한 WORKER_INTERRUPTED 실패로 종료하고 관리자 수동 재시도를 허용한다.
- Job의 QUEUED→RUNNING은 조건부 UPDATE로 원자적으로 선점한다. scoring/점수 commit/오류 처리 전에
  DB row lock과 attempts/status를 확인해 오래된 실행의 점수·실패 덮어쓰기를 막는다.
  보장은 **점수 저장 1회**이며, 중단 전후 계산 자체는 재실행될 수 있다.
- scratch를 `work/<job UUID>-<attempt>`로 분리하고 재시도 선점 후 과거 scratch를 정리한다.
  성공 점수 commit 이후 기존 artifact 삭제 순서와 개인정보 allowlist는 유지했다.
- `.env.example`의 CORS_ORIGINS를 Pydantic이 받는 JSON 배열로 수정했다. 기존 문자열은 SettingsError로
  API 기동을 막는다. 예제 파일을 Settings로 읽는 검증은 통과했다.
- Starlette는 1 MiB를 넘는 multipart 파일을 `/tmp`에 spool한다. Compose API의 기존 128 MiB tmpfs는
  405 MB Lab2 ZIP을 수용할 수 없어 1 GiB로 조정했다. noexec/nosuid/nodev는 유지했다.
  Docker에서 실제 대용량 업로드·동시 업로드 용량 검증은 남아 있다.

회수는 즉시 수행되지 않는다. 예를 들어 timeout=60초이면 선점 시점으로부터 90초가 지난 후
다음 sweep에서 재시도된다. sweep은 Job 사이에 실행하므로 다른 긴 평가가 실행 중이면 더 늦어진다.
Worker가 아예 꺼져 있는 동안에는 복구/평가가 진행되지 않는다. 한 Worker의 동시성은 계속 1이다.
회수 판단은 Task의 현재 timeout과 서버 UTC 시간을 사용하므로 실행 중 timeout을 바꾸지 말고
서버 시간을 동기화한다. 이 검증은 전체 DB/Redis 장애·네트워크 파티션·다수 Worker 부하 시험을 대체하지 않는다.

## Docker 사용자가 할 조치

Docker Desktop을 설치·기동하고 `docker version`, `docker compose version`, `docker info`가
성공하는지 확인한다. `.env.example`을 별도 테스트용 `.env`로 복사하고 테스트 전용 project/volume/port로
`docker compose config`, build/up, migration, healthcheck, 업로드를 검증한다.
원래 DB/volume에 바로 migration하거나 이번 smoke Task를 운영 Task로 바꾸지 않는다.
현재 backend Dockerfile은 `requirements.txt`만 설치하므로 Lab02 의존성이 없다.
Lab02 이미지에는 별도로 `requirements-lab02.txt`와 준비된 resources/data read-only mount가 필요하다.
이 Docker/GPU 이미지와 per-Job 격리 컨테이너는 아직 구현·검증 완료 상태가 아니다.

## 사용자 브라우저 검증 체크리스트

API 검증 통과를 아래 화면 검증 통과로 간주하지 않는다. 합성 수강생·테스트 Task·테스트 파일 사본을 사용한다.

1. 로그아웃 상태에서 Tasks/Submit/Leaderboard 접근, 학생 회원가입·로그인 요구가 없는지 확인한다.
2. 제출 폼의 학번 비공개·첫 닉네임/이모지 고정·연습 사이트·LMS 안내와 ZIP 크기 표시를 확인한다.
3. Baseline 업로드: Notebook/ZIP 선택, 진행률, 업로드 중 버튼 비활성화, 결과 페이지 전환,
   QUEUED→RUNNING→COMPLETED·Macro F1 표시를 확인한다.
4. 같은 합성 학번으로 Development 업로드 후 닉네임/이모지가 유지되고 리더보드 1행의
   Baseline·최고 Development·improvement가 API 값과 같은지 확인한다.
5. 파일 누락, 잘못된 확장자, 크기 초과, 잘못된 ZIP, 미등록 합성 학번을 제출한다.
   안전한 실패 안내와 재시도 가능한 폼을 확인한다. 중복 업로드를 만들지 않는다.
6. 공개 리더보드·상세·내 제출·프로필에 학번/실명/원본 파일명/서버 경로/내부 오류가 없는지 확인한다.
   닉네임·모델명에는 개인정보를 입력하지 않는다.
7. 내 제출은 현재 브라우저에 저장된 UUID만 표시하는지, 새 브라우저/저장소 삭제 시 자동 기록이
   없어지는지 확인한다. localStorage 차단 시에도 제출이 되는지 확인한다.
8. 익명 `/admin`, `/admin/participants`, `/admin/jobs` 직접 접근이 관리자 로그인/권한 화면으로
   제한되는지 확인한다. 익명 CSV·파일 API 거부는 이번 실제 HTTP 검증에서 확인했다.
9. 합성 관리자로 로그인해 Participants/Jobs/Submissions에서 합성 학번, 점수, 상태,
   자동 삭제 안내를 확인한다. 성공 파일 다운로드·재평가가 차단되는지 확인한다.
10. 관리자 CSV 버튼으로 다운로드하고 UTF-8 한글·이모지, 학번 선행 0, Baseline/Development/
    improvement/건수를 확인한다. 스프레드시트에서 학번 열을 Text로 읽는다.
11. 관리자 로그아웃 후 페이지 이동/새로고침해 관리자 정보가 다시 노출되지 않는지 확인한다.

## Lab2 Notebook ↔ evaluator 대조

원본: `/Users/yanghyein/Downloads/Lab2_Sentiment_Analysis_solution.ipynb`.
SHA-256 `890e47c6e47c81e1894ca4412a4e7ba29932eb5e8a5215645c78d6ab2f39a73a`.
원본 ZIP SHA-256 `526122c7997ec714b728accb702f0e503332d213b01ce310556b635a7798cb18`.
사본 사용 전후 원본과 사본 해시 일치를 확인했다. 원본은 수정하지 않았다.

| 항목 | Notebook | evaluator / 판정 |
|---|---|---|
| 모델 | google-bert/bert-base-uncased, AutoModelForSequenceClassification | 고정 BertForSequenceClassification / 일치 |
| revision | 모델·tokenizer 로딩에 revision 없음(셀 13,17) | 둘 다 `86b5e0934494bd15c9632b12f734a8a67f723594` 고정 / 불일치 |
| 라벨 | 0 negative, 1 positive; config·manifest 동일 | 동일 / 일치 |
| tokenizer | AutoTokenizer 기본 fast, uncased 모델 | 서버 BertTokenizerFast·local only / 모델 계열 일치, revision 고정 필요 |
| 길이·텍스트 | MAX_LENGTH=128, truncation=True, 원문 입력 | 특수 토큰 포함128, right truncation, 원문 / 일치. Notebook도 use_fast=True와 truncation_side=right 명시 권장 |
| manifest | format_version 1.0, sentiment, full_model, num_labels=2, label_mapping | 동일. revision 필드 추가 요구 없음 |
| ZIP | 루트 manifest.json/config.json/model.safetensors만 생성 | 동일. tokenizer/코드/optimizer 금지 유지 |
| 크기 | export max_shard_size=2GB, ZIP 크기 출력만 수행 | Task 기본 압축 크기 및 총 해제 크기 각각 500,000,000 bytes 이하. shard 설정은 ZIP 허용 한도가 아님 |
| 실제 ZIP | 압축 405,585,228 / 해제 합계 437,959,720 bytes | 테스트 Task 기본500 MB 한도 통과. Notebook 자체 한도 기본20,000,000 bytes |
| 지표 | Accuracy·전체 validation Macro F1(labels=[0,1], zero_division=0) | 동일 계산식, 평가 데이터는 다름 |

배포 전 Notebook 모델/tokenizer 두 from_pretrained 호출에 같은 고정 revision을 넣고 배포 사본을
확정해야 한다. Notebook은 라이브러리 범위 설치, 서버는 정확한 버전 고정이므로 동일 환경 재현도 별도 확인한다.
Notebook IMDb train 로딩도 revision이 없으며 서버는 고정 IMDb public test를 사용한다.
추가 불일치: Notebook은 리더보드 평가셋을 비공개라고 설명하지만 현재는 임시 IMDb **public test**이다.
Notebook 내 공식 보고서 안내도 앞부분의 별도 개발보고서와 뒷부분의 최종 Notebook 내 요약이 상충하며,
사이트의 별도 개발보고서 안내와도 다르다. 수업 정책을 확정한 뒤 배포 문구를 통일해야 한다.

## 12시간 미사용 종료를 전제로 한 운영 배치

현재 코드에 맞는 배치는 아래와 같다. 실제 서버 주소·공급자·미사용 판단 방식·디스크 유지 여부는
아직 정해지지 않았고 이 보고서에서 가정하지 않는다.

| 위치 | 유지할 것 | 코드상 연결/제약 |
|---|---|---|
| GPU와 독립된 상시 서버/서비스 | API, PostgreSQL, Redis, frontend/reverse proxy | API는 GPU 없이 업로드·검증·Queue·결과 제공 가능. DB/Redis는 인터넷에 직접 노출하지 않고 인증된 사설 경로 사용 |
| GPU 수명과 독립된 영속 저장소 | incoming/artifacts/quarantine, 백업 | 구현은 LocalArtifactStorage뿐. API와 원격 Worker가 같은 POSIX 저장소를 마운트해야 함. GPU 로컬 디스크만을 원본 저장소로 사용하면 안 됨 |
| GPU 인스턴스 | Worker, 준비된 resources/data, Job scratch | DB/Redis로 outbound 접속. API/DB를 GPU 인스턴스에서 함께 종료시키지 않음. concurrency=1 유지 |

동일 호스트 Compose named volume은 다른 GPU 호스트에 자동 공유되지 않는다. 현재 S3/object-storage
adapter나 artifact 전송/download Worker 프로토콜은 없다. 그대로 운영하려면 양쪽에 공유 POSIX
파일시스템을 같은 절대 STORAGE_ROOT로 마운트하고 API와 Worker의 UID/권한·atomic rename·삭제 동작을
확인해야 한다. object storage를 선택하면 adapter/전송·삭제/권한 구현이 선행되어야 한다.
quarantine을 Job child에게 노출하지 않으며, child에는 해당 Job artifact와 dataset/resources만 read-only로 제공한다.

연결할 설정은 DATABASE_URL, REDIS_URL, QUEUE_NAME, STORAGE_ROOT, LAB02_RESOURCES_ROOT와
Task dataset_config의 절대 path/metadata_path이다. DB와 Redis 주소는 실제 인프라 확정 후 설정한다.
API와 Worker의 LAB02_DEVICE/BATCH_SIZE/SEED는 동일해야 한다. evaluator identity에 device/batch/seed가
포함되므로 API는 cpu, Worker는 cuda이면 현재 점수가 집계에서 제외된다. CPU smoke Task는 운영 점수로
이전하지 않는다. API에 CUDA 하드웨어가 있어야 한다는 뜻은 아니다.

GPU가 꺼져도 API는 QUEUED를 유지한다. Worker가 돌아오면 DB sweep으로 유실 dispatch와 만료 실행을
복구한다. 종료 전에 가능하면 신규 dequeue를 멈추고 진행 중 Job을 끝내며, 강제 종료에도 검증된 재시도 경로를 사용한다.
무의미한 keepalive가 공급자의 미사용 종료를 막는다는 주장은 하지 않는다.
Redis는 현재 Compose에 영속 volume/AOF가 없다. 운영에서는 영속화/복구 정책을 정하고,
PostgreSQL과 artifact의 시점이 맞는 백업·복원 시험을 수행한다. DB 재dispatch는 백업을 대신하지 않는다.

## GPU 할당 후 남은 작업과 사용자 결정

남은 검증: CUDA/PyTorch 이미지 호환, pinned resources/data read-only mount, 단일 Job no-network/non-root
컨테이너 경계, fail-closed 실제 malware scanner, GPU OOM/timeout/중단 복구, 실제 ZIP smoke,
전체 25,000 IMDb 평가 시간/메모리 측정과 timeout/batch 확정, Docker 대용량 업로드·권한·자원 한도,
HTTPS/인증·백업/복원·모니터링, 위 브라우저 체크리스트. 실제 운영 Task 활성화는 이 검증 이후에 한다.

사용자 결정 사항:

- GPU와 별개로 API·DB·Redis를 상시 유지할 서버/관리형 서비스, 실제 주소·도메인·사설 연결 경로.
- 원격 GPU와 공유할 영속 POSIX 저장소 또는 object-storage adapter 개발 여부, 용량·백업·보관 정책.
- 공급자의 정확한 12시간 종료 조건, 재기동 방식, GPU 디스크/마운트 보존 조건. 공급자 문서로 확인할 사항이다.
- GPU 비용/가동 시간과 평가 대기시간 목표, 장애 알림·운영 담당자.
- Notebook revision/공개 평가 데이터 설명·LMS 제출물 정책을 통일할 배포본.

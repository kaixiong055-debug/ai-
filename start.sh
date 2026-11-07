#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v java >/dev/null 2>&1; then
  echo '未找到 Java，请先安装 Java 17 或 21。' >&2
  exit 1
fi
if [[ -z "${GAME_ADMIN_PASSWORD:-}" || "$GAME_ADMIN_PASSWORD" == 'CHANGE_ME_BEFORE_STARTING' ]]; then
  echo '请先设置 GAME_ADMIN_PASSWORD（至少12字符），再启动。部署环境变量说明见 README.md。' >&2
  exit 1
fi
jar_path="${CMS_JAR:-game-cms.jar}"
if [[ ! -f "$jar_path" ]]; then
  jar_path="target/game-cms-1.0.0.jar"
fi
if [[ ! -f "$jar_path" ]]; then
  echo '未找到运行包；源码目录请先执行 mvn clean package，或使用已构建的部署包。' >&2
  exit 1
fi
exec java -Xms128m -Xmx512m -jar "$jar_path"

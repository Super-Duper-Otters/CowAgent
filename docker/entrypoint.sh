#!/bin/bash
set -e

CHATGPT_ON_WECHAT_PREFIX=${CHATGPT_ON_WECHAT_PREFIX:-/app}
CHATGPT_ON_WECHAT_CONFIG_PATH=${CHATGPT_ON_WECHAT_CONFIG_PATH:-$CHATGPT_ON_WECHAT_PREFIX/config.json}
CHATGPT_ON_WECHAT_EXEC=${CHATGPT_ON_WECHAT_EXEC:-"python app.py"}

run_migrations() {
    if [ "${COWAGENT_RUN_MIGRATIONS:-true}" = "true" ]; then
        echo "[entrypoint] Running database migrations..."
        python -c "from business.schema.storage import initialize_storage; initialize_storage()"
    fi
}

start_app() {
    cd "$CHATGPT_ON_WECHAT_PREFIX"
    run_migrations
    exec $CHATGPT_ON_WECHAT_EXEC
}

export CHATGPT_ON_WECHAT_PREFIX
export CHATGPT_ON_WECHAT_CONFIG_PATH
export CHATGPT_ON_WECHAT_EXEC
export COWAGENT_RUN_MIGRATIONS

if [ "$(id -u)" = "0" ]; then
    mkdir -p /home/agent/cow
    chown -R agent:agent /home/agent/cow
    exec su agent -s /bin/bash -c "$(declare -f run_migrations start_app); start_app"
fi

start_app

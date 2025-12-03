PROVIDER="local" #  [local, gemini]
LOCAL_URL="http://10.201.24.88:6655/v1"

python src/real_world/bot_listener_for_1_repo.py \
    --provider $PROVIDER \
    --local_url $LOCAL_URL
PROVIDER="gemini" #  [local, gemini, claude]
LOCAL_URL="https://6cd2128b5715.ngrok-free.app/v1"

python src/real_world/bot_listener_all.py \
    --provider $PROVIDER \
    --local_url $LOCAL_URL
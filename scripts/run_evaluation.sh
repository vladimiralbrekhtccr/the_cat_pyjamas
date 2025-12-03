PROVIDER="local" #  [local, gemini]
GROUP_PATH="vladimiralbrekhtccr-group" # evaluation_pipeline_test
LOCAL_URL="http://10.201.24.88:6655/v1"

python src/evaluation/run_evaluation.py \
    --provider $PROVIDER \
    --group_path $GROUP_PATH \
    --local_url $LOCAL_URL


PROVIDER="local" #  [local, gemini]
GROUP_PATH="vladimiralbrekhtccr-group" #

python src/evaluation/run_evaluation.py \
    --provider $PROVIDER \
    --group_path $GROUP_PATH

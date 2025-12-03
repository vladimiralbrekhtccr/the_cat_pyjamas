# Model and environment settings
export CUDA_VISIBLE_DEVICES=0,1

MODEL="/home/vladimir_albrekht/projects/temp_f_cats/large_files/Qwen3-30B-A3B-Instruct-2507"


MODEL_SERVED_NAME="qwen3_30b_deployed" 
PORT=6655
HOST="0.0.0.0"
SEED=0

# vLLM configuration parameters
GPU_MEMORY_UTILIZATION=0.90
TENSOR_PARALLEL_SIZE=2 # amount of gpus to use for splitting
DTYPE="auto"
MAX_NUM_BATCHED_TOKENS=32768
MAX_MODEL_LEN=8196
KV_CACHE_DTYPE="auto"
MAX_NUM_SEQS=50


CMD="vllm serve $MODEL \
  --tokenizer "$MODEL" \
  --host $HOST \
  --port $PORT \
  --served-model-name $MODEL_SERVED_NAME \
  --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
  --max-num-batched-tokens $MAX_NUM_BATCHED_TOKENS \
  --max-model-len $MAX_MODEL_LEN \
  --trust-remote-code \
  --dtype $DTYPE \
  --tensor-parallel-size $TENSOR_PARALLEL_SIZE \
  --kv-cache-dtype $KV_CACHE_DTYPE \
  --max-num-seqs $MAX_NUM_SEQS \
  --seed $SEED"

# Execute the command
eval $CMD 2>&1 | tee full_output.log
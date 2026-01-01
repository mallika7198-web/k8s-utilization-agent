from typing import List, Dict


def compute_fragmentation(free_cpu_blocks: List[float], free_mem_blocks: List[float]) -> Dict[str, object]:
    """
    Compute simple fragmentation metrics given lists of free CPU blocks (cores) and free memory blocks (bytes).

    Returns:
      - largest_free_cpu_block
      - largest_free_memory_block
      - fragmentation_type: 'CPU' | 'Memory' | 'Both' | 'None'

    Deterministic rule:
      - If largest_free_cpu_block < 0.5 * sum(free_cpu_blocks) then CPU fragmentation exists
      - If largest_free_memory_block < 0.5 * sum(free_mem_blocks) then Memory fragmentation exists
      - Combine to determine fragmentation_type
    """
    total_cpu = sum(free_cpu_blocks) if free_cpu_blocks else 0.0
    total_mem = sum(free_mem_blocks) if free_mem_blocks else 0.0
    largest_cpu = max(free_cpu_blocks) if free_cpu_blocks else 0.0
    largest_mem = max(free_mem_blocks) if free_mem_blocks else 0.0

    cpu_frag = False
    mem_frag = False
    if total_cpu > 0:
        cpu_frag = largest_cpu <= 0.5 * total_cpu
    if total_mem > 0:
        mem_frag = largest_mem <= 0.5 * total_mem

    if cpu_frag and mem_frag:
        frag_type = 'Both'
    elif cpu_frag:
        frag_type = 'CPU'
    elif mem_frag:
        frag_type = 'Memory'
    else:
        frag_type = 'None'

    return {
        'largest_free_cpu_block': largest_cpu,
        'largest_free_memory_block': largest_mem,
        'fragmentation_type': frag_type,
    }

from normalize.fragmentation import compute_fragmentation


def test_fragmentation_none():
    cpu_blocks = [4.0, 2.0]
    mem_blocks = [1024.0, 512.0]
    r = compute_fragmentation(cpu_blocks, mem_blocks)
    assert r['fragmentation_type'] == 'None'
    assert r['largest_free_cpu_block'] == 4.0


def test_fragmentation_cpu():
    cpu_blocks = [1.0, 1.0, 1.0]
    mem_blocks = [2048.0]
    r = compute_fragmentation(cpu_blocks, mem_blocks)
    assert r['fragmentation_type'] == 'CPU'
    assert r['largest_free_cpu_block'] == 1.0


def test_fragmentation_both():
    cpu_blocks = [1.0, 1.0]
    mem_blocks = [512.0, 512.0]
    r = compute_fragmentation(cpu_blocks, mem_blocks)
    assert r['fragmentation_type'] == 'Both'

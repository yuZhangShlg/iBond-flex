import signal
import time
from flex.api import RSA_SAL
from logging import getLogger
from multiprocessing import Process, Queue

from caffeine.alignment.sample_align import SampleAligner
from caffeine_tests.config import fed_conf_guest_no_coordinator
from caffeine_tests.config import fed_conf_host_no_coordinator

logger = getLogger('Alignment')

test_cases = {
    
    #with third party
    'mock_small_rsa': {
        'guest': {
            'input': {
                'fed_conf': fed_conf_guest_no_coordinator,
                'id_cols': [['1', '2', '333']],
                'align_method': RSA_SAL,
                'security': [['rsa', {'key_length': 2048}]]
            },
            'timeout': 60,
            'expect': [['1', '333']]
        },
        'host': {
            'input': {
                'fed_conf': fed_conf_host_no_coordinator,
                'id_cols': [['333', '22', '1']],
                'align_method': RSA_SAL,
                'security': [['rsa', {'key_length': 2048}]]
            },
            'timeout': 60,
            'expect': [['1', '333']]  # <- the order is decided by guest data.
        },
    },
    'mock_multicolumn': {
        'guest': {
            'input': {
                'fed_conf': fed_conf_guest_no_coordinator,
                'id_cols': [['1', '2', '333'],['1','2','333']],
                'align_method': RSA_SAL,
                'security': [['rsa', {'key_length': 2048}]]
            },
            'timeout': 60,
            'expect': [['1', '333'],['1','333']]
        },
        'host': {
            'input': {
                'fed_conf': fed_conf_host_no_coordinator,
                'id_cols': [['333', '22', '1'],['333','22','1']],
                'align_method': RSA_SAL,
                'security': [['rsa', {'key_length': 2048}]]
            },
            'timeout': 60,
            'expect': [['1', '333'],['1','333']]  # <- the order is decided by guest data.
        },
    },

}


def run(input, role, share_queue, expect=None, casename='', timeout=60):
    fed_conf = input['fed_conf']
    job_id_prefix = fed_conf['session']['job_id']
    fed_conf['session']['job_id'] = job_id_prefix + casename

    aligner = SampleAligner(input['align_method'], input['fed_conf'], input['security'])
    out = aligner.align(input['id_cols'])
    if role in ['guest', 'host']:
        share_queue.put(out)


def test_alignment():
    def timeout_handler(signum, frame):
        logger.info(f'Timeout!')
        for p in process_list:
            p.terminate()
        raise Exception('Case Error!')

    share_queue = Queue()
    for test_name, test_case in test_cases.items():
        #if test_name in ['mock_small',
        # 'mock_small_wo_cooridinator', 'mock_multicolumn_wo_coordinator']:
        if False:
             continue
        else:
             logger.info(test_name)

        logger.info(f'!!!Start to test {test_name}.')

        process_list = []
        try:
            casename_postfix = str(time.time())
            for role, config in test_case.items():
                config['casename'] = test_name + casename_postfix
                config['share_queue'] = share_queue
                config['role'] = role
                timeout = config.get('timeout', 60)
                p = Process(target=run, kwargs=config)
                p.start()
                process_list.append(p)

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)

            for p in process_list:
                p.join()
            out_list = []
            for i in range(0, share_queue.qsize()):
                out_list.append(share_queue.get())
            for index in range(1, len(out_list)):
                assert out_list[0] == out_list[index]
                logger.info(f'ref {out_list[0]} target {out_list[index]}')
            logger.info(f'Testcase {test_name} finished!!!')
            signal.alarm(0)
        except KeyboardInterrupt:
            logger.info(f'User Interrupt!')
            for p in process_list:
                p.terminate()
            break

            
        logger.info(f'Testcase {test_name} finished!!!')

if __name__ == '__main__':
    test_alignment()

    """
    for i in range(20):
        logger.info(f"For {i}th iteration....")
        test_alignment()
    """
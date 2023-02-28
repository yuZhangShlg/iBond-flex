from multiprocessing import Process
from logging import getLogger
from typing import Dict

import time
import signal
import pandas as pd
import numpy as np
import json

from caffeine.utils import IBondDataFrame, Middleware
from caffeine_tests.config import fed_conf_coordinator_mp, fed_conf_guest_mp, fed_conf_host0_mp, fed_conf_host1_mp
from caffeine_tests.config import fed_conf_host, fed_conf_guest, fed_conf_coordinator

logger = getLogger('Feature_selection_tester')


def hetero_case_template(train_files, test_files, descs, meta_params, selector, feat_infos, config, timeout = 1200):
    return {
        'guest': {
            'input': {
                'selector': selector[0],
                'feat_infos': feat_infos[0],
                'config': config[0],
                'fed_conf': fed_conf_guest,
                'role': 'guest', 
                'train_csv': train_files[0],
                'verify_csv': test_files[0],
                'csv_desc': descs[0],
                'meta_params': meta_params,
            },
            'timeout': timeout
        },
        'host': {
            'input': {
                'selector': selector[1],
                'feat_infos':  feat_infos[1],
                'config': config[1],
                'fed_conf': fed_conf_host,
                'role': 'host', 
                'train_csv': train_files[1],
                'verify_csv': test_files[1],
                'csv_desc': descs[1],
                'meta_params': meta_params,
            },
            'timeout': timeout
        },
        'coordinator': {
            'input': {
                'selector': selector[2],
                'feat_infos': feat_infos[-1],
                'fed_conf': fed_conf_coordinator,
                'config': config[3],
                'role': 'coordinator', 
                'meta_params': meta_params,
            },
            'timeout': timeout
        }
    }

def hetero_case_template_multihost(train_files, test_files, descs, meta_params, selector, feat_infos, config, timeout = 1200):
    return {
        'guest': {
            'input': {
                'selector': selector[0],
                'feat_infos': feat_infos[0],
                'config': config[0],
                'fed_conf': fed_conf_guest_mp,
                'role': 'guest', 
                'train_csv': train_files[0],
                'verify_csv': test_files[0],
                'csv_desc': descs[0],
                'meta_params': meta_params,
            },
            'timeout': timeout
        },
        'host1': {
            'input': {
                'selector': selector[1],
                'feat_infos': feat_infos[1],
                'config': config[1],
                'fed_conf': fed_conf_host0_mp,
                'role': 'host', 
                'train_csv': train_files[1],
                'verify_csv': test_files[1],
                'csv_desc': descs[1],
                'meta_params': meta_params,
            },
            'timeout': timeout
        },
        'host2': {
            'input': {
                'selector': selector[1],
                'feat_infos': feat_infos[2],
                'config': config[2],
                'fed_conf': fed_conf_host1_mp,
                'role': 'host', 
                'train_csv': train_files[2],
                'verify_csv': test_files[2],
                'csv_desc': descs[2],
                'meta_params': meta_params,
            },
            'timeout': timeout
        },
        'coordinator': {
            'input': {
                'selector': selector[2],
                'feat_infos': feat_infos[-1],
                'fed_conf': fed_conf_coordinator_mp,
                'config': config[3],
                'role': 'coordinator', 
                'meta_params': meta_params,
            },
            'timeout': timeout
        }
    }

def load_data(data, desc, middleware):
    if data is not None:
        pdf = pd.read_csv(data).iloc[:200000]
        data = middleware.create_dataframe(
            pdf,
            desc
        )
    else:
        pdf = pd.DataFrame([])
        data = middleware.create_dataframe(
            pdf,
            None
        )
    return data

def tmp_stat(data_stas_csv, data_desc):
    from caffeine.feature.feature_engineering.ibond_feature_df import FeatureDataFrame
    stat = pd.read_csv(data_stas_csv)
    return FeatureDataFrame(stat, data_desc)


def hetero_run(casename, input, expect=None, timeout=1200):
    middleware = Middleware(config=input.get('config')).session
    role = input['role']

    fed_conf = input.get('fed_conf')
    fed_conf['session']['job_id'] = fed_conf['session']['job_id']+casename

    meta_params = input.get('meta_params', {}).get('train_param')
    meta_params['process_method'] = 'hetero'

    train_meta_params = {
        'train_param': meta_params,
        'security_param': input.get('meta_params', {}).get('security_param'),
        'federal_info': input.get('fed_conf')
    }

    logger.info(f'>>>> meta_params {meta_params}')

    pure_predict_meta_params = {
        'predict_param': input.get('meta_params', {}).get('predict_param', {})
    }

    selector_class = input.get('selector')
    selector = selector_class(train_meta_params, middleware)

    if role in ['guest', 'host']:
        # get and process data
        
        train_data = load_data(
            input.get('train_csv'), input.get('csv_desc'), middleware)      
        verify_data = load_data(input.get('verify_csv'), input.get('csv_desc'), middleware)

        feat_infos = input.get('feat_infos')
        with open(feat_infos, 'r') as fin:
            feat_infos = json.loads(fin.readlines()[0])

        # train
        output, model_infos = selector.train(train_data, verify_data, feat_infos)

        saved_model = middleware.load_model(model_infos[-1].model_id)
        # logger.info(f'moddelware_load_model:{saved_model}')
        learner_reload = selector_class(
            pure_predict_meta_params,
            middleware,
            model_info = saved_model
        )
        train_data_reload = load_data(
            input.get('train_csv'), input.get('csv_desc'), middleware)  
        process_test_data_reload = learner_reload.predict(train_data_reload)

        data = output['data'].to_pandas()

        data1 = process_test_data_reload.to_pandas()
        logger.info(f'data {data}')

        logger.info(f'data1 {data1}')
        assert (data == data1).to_numpy().all()        

    elif role == 'coordinator':
        # train 
        feat_infos={'name': []}
        selector.train(None, None, feat_infos=feat_infos)
   

    logger.info(f'Run ended for {casename} {role}.')


def multihost_hetero_run_processes(test_cases):
    for test_name, test_case in test_cases.items():
        logger.info(f'!!!Start to test {test_name}.')

        process_list = []
        try:
            for role, config in test_case.items():
                timeout = config.get('timeout', 300)
                config['casename'] = test_name
                p = Process(target=hetero_run, kwargs=config)
                p.start()
                process_list.append(p)

            def timeout_handler(signum, frame):
                logger.info(f'Timeout!')
                for p in process_list:
                    p.terminate()
                raise Exception('Case Error!')

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)

            for p in process_list:
                p.join()

            logger.info(f'Testcase {test_name} finished!!!')
            signal.alarm(0)
        except KeyboardInterrupt:
            logger.info(f'User Interrupt!')
            for p in process_list:
                p.terminate()
            break

def hetero_run_processes(test_cases):
    import sys
    role = sys.argv[1]
    for test_name, test_case in test_cases.items():
        try:
            hetero_run(test_name, test_case[role]['input'])
        except KeyboardInterrupt:
            logger.info(f'User Interrupt!')
            break
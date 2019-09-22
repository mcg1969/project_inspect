from project_inspect import config, project

import pandas as pd
from os.path import dirname, join, abspath

import sys
import pytest
import subprocess
import itertools

PROJECT_ROOT = join(dirname(dirname(__file__)), 'test_node')
config.PROJECT_ROOT = PROJECT_ROOT


@pytest.fixture(scope="session")
def master_df():
    return project.build_node_inventory()


def test_inventory_hierarchy(master_df):
    master_df2 = project.build_node_inventory(PROJECT_ROOT)
    assert master_df.equals(master_df2)
    for owner_name, owner_group in master_df.groupby('owner'):
        owner_df = project.build_owner_inventory(owner_name, project_root=PROJECT_ROOT)
        owner_df2 = project.build_owner_inventory(join(PROJECT_ROOT, owner_name))
        assert owner_df.equals(owner_df2)
        assert owner_df.equals(owner_group.reset_index(drop=True))
        for (owner_name, project_name), project_group in owner_df.groupby(['owner', 'project']):
            project_df = project.build_project_inventory(owner_name, project_name, project_root=PROJECT_ROOT)
            project_df2 = project.build_project_inventory(join(PROJECT_ROOT, owner_name, project_name))
            assert project_df.equals(project_df2)
            assert project_df.equals(project_group.reset_index(drop=True))


def test_user1_Portfolio(master_df):
    df = master_df[(master_df.owner == 'user1') & (master_df.project == 'Portfolio')]
    assert set(df.environment) == {'default'}
    assert set(df.package[df.requested]).issuperset({'bokeh', 'cvxopt', 'ipykernel', 'matplotlib',
                                                     'pandas', 'psutil', 'python', 'r-base',
                                                     'r-dplyr', 'r-ggplot2', 'r-irkernel', 'r-yaml',
                                                     'ruamel.ordereddict', 'ruamel.yaml',
                                                     'statsmodels', 'toolz', 'attrs'})
    assert all(df.build[df.package.str.startswith('ruamel.')] == '<pip>')
    assert any(~df.requested & df.required)
    assert any(~df.requested & ~df.required)


def test_user1_ScriptsOnly(master_df):
    df = master_df[(master_df.owner == 'user1') & (master_df.project == 'ScriptsOnly')]
    assert set(df.environment) == {'default', 'python'}
    df1 = df[df.environment == 'default']
    assert set(df1.package[df1.requested]) == {'python', 'r-base', 'r-repr'}
    assert any(~df1.requested & df1.required)
    assert any(~df1.requested & ~df1.required)
    df2 = df[df.environment == 'python']
    assert set(df2.package[df2.requested]) == {'python', 'pyyaml'}
    assert any(~df2.requested & df2.required)
    assert any(~df2.requested & ~df2.required)


def test_user2_ProjectInspector(master_df):
    df = master_df[(master_df.owner == 'user2') & (master_df.project == 'ProjectInspector')]
    assert set(df.environment) == {'default'}
    assert set(df.package[df.requested]) == {'ipykernel', 'ipython', 'pandas', 'python',
                                             'r-base', 'r-irkernel', 'rpy2', 'numpy-base',
                                             'setuptools'}
    assert any(~df.requested & df.required)
    assert any(~df.requested & ~df.required)


def test_user2_ScriptsOnly(master_df):
    df1 = master_df[(master_df.owner == 'user1') & (master_df.project == 'ScriptsOnly')].reset_index(drop=True).drop('owner', axis=1)
    df2 = master_df[(master_df.owner == 'user2') & (master_df.project == 'ScriptsOnly')].reset_index(drop=True).drop('owner', axis=1)
    assert df1.equals(df2)


def _read_csv(fp):
    return pd.read_csv(fp, converters={'required_by': str},
                       dtype={'required': bool, 'requested': bool},
                       index_col=None)


def test_cli_nosummary(master_df):
    cmd = ['python', '-m', 'project_inspect', '--root', PROJECT_ROOT]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outp, errp = proc.communicate()
    assert 'user2/NoEnvs/cannot_read.py: CANNOT READ' in errp.decode()
    from io import BytesIO
    df = _read_csv(BytesIO(outp))
    assert df.equals(master_df)


def test_cli_filter(master_df):
    fpath = join(dirname(__file__), 'pfilt')
    cmd = ['python', '-m', 'project_inspect', '--root', PROJECT_ROOT, '--package-file', fpath]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outp, errp = proc.communicate()
    assert 'user2/NoEnvs/cannot_read.py: CANNOT READ' in errp.decode()
    from io import BytesIO
    df = _read_csv(BytesIO(outp))
    filtered_df = master_df[(master_df.package=='xlrd')|(master_df.package=='pytest')].reset_index(drop=True)
    assert df.equals(filtered_df)


@pytest.mark.parametrize('project_group, package_group',
    itertools.product(('all', 'node', 'owner', 'project', 'environment'),
                      ('all', 'package', 'version')))
def test_summary(master_df, project_group, package_group):
    def _clean(df):
        df = df[df['requested'] if 'requested' in df.columns else df['n_requested'] != 0]
        for col in ('version', 'n_versions', 'required', 'n_required', 'requested', 'n_requested'):
            if col in df.columns:
                del df[col]
        return df.reset_index(drop=True)
    if package_group == 'version':
        pytest.xfail('Versions can differ')
    fpdir = join(dirname(__file__), sys.platform)
    expected = _read_csv('{}/{}_{}.csv'.format(fpdir, project_group, package_group))
    expected = _clean(expected)
    summary = project.summarize_data(master_df, '{}/{}'.format(project_group, package_group))
    summary = _clean(summary)
    if not summary.equals(expected):
        print(summary)
        print(expected)
    assert summary.equals(expected)


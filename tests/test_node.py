from project_inspect.project import build_project_inventory, build_user_inventory, build_node_inventory
from project_inspect import config

import pandas as pd
from os.path import dirname, join

import pytest

config.PROJECT_HOME = join(dirname(dirname(__file__)), 'test_node')


@pytest.fixture(scope="session")
def master_df():
    return build_node_inventory()


def test_inventory_hierarchy(master_df):
    master_df2 = build_node_inventory(config.PROJECT_HOME)
    assert master_df.equals(master_df2)
    for user, user_group in master_df.groupby('user'):
        user_df = build_user_inventory(user)
        user_df2 = build_user_inventory(join(config.PROJECT_HOME, user))
        assert user_df.equals(user_df2)
        for project, project_group in user_df.groupby('project'):
            project_df = build_project_inventory(user, project)
            project_df2 = build_project_inventory(join(config.PROJECT_HOME, user, project))
            assert project_df.equals(project_group.drop(['project'], axis=1))


def test_user1_Portfolio(master_df):
    df = master_df[(master_df.user == 'user1') & (master_df.project == 'Portfolio')]
    assert set(df.env) == {'default'}
    assert set(df.package[df.requested]) == {'bokeh', 'cvxopt', 'ipykernel', 'matplotlib',
                                             'pandas', 'psutil', 'python', 'r-base',
                                             'r-dplyr', 'r-ggplot2', 'r-irkernel', 'r-yaml',
                                             'ruamel.ordereddict', 'ruamel.yaml',
                                             'statsmodels', 'toolz'}
    assert any(~df.requested & df.required)
    assert any(~df.requested & ~df.required)


def test_user1_ScriptsOnly(master_df):
    df = master_df[(master_df.user == 'user1') & (master_df.project == 'ScriptsOnly')]
    assert set(df.env) == {'default', 'python'}
    df1 = df[df.env == 'default']
    assert set(df1.package[df1.requested]) == {'python', 'r-base', 'r-repr'}
    assert any(~df1.requested & df1.required)
    assert any(~df1.requested & ~df1.required)
    df2 = df[df.env == 'python']
    assert set(df2.package[df2.requested]) == {'python', 'pyyaml'}
    assert any(~df2.requested & df2.required)
    assert any(~df2.requested & ~df2.required)


def test_user2_ProjectInspector(master_df):
    df = master_df[(master_df.user == 'user2') & (master_df.project == 'ProjectInspector')]
    assert set(df.env) == {'default'}
    assert set(df.package[df.requested]) == {'ipykernel', 'ipython', 'pandas', 'python',
                                             'r-base', 'r-irkernel', 'rpy2'}
    assert any(~df.requested & df.required)
    assert any(~df.requested & ~df.required)


def test_user2_ScriptsOnly(master_df):
    df1 = master_df[(master_df.user == 'user1') & (master_df.project == 'ScriptsOnly')]
    df2 = master_df[(master_df.user == 'user2') & (master_df.project == 'ScriptsOnly')]
    assert df1.drop('user', axis=1).equals(df2.drop('user', axis=1))






# -----------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# -----------------------------------------------------------------------------

# pylint: disable=no-else-return

import time
from collections import defaultdict
from importlib import import_module

import packaging.version
from knack.log import get_logger

from azdev.operations.statistics import _create_invoker_and_load_cmds  # pylint: disable=protected-access
from azdev.utilities import require_azure_cli, get_path_table, display, heading, output

logger = get_logger(__name__)


class BreakingChangeItem:
    def __init__(self, module, command, detail, target_version):
        self.module = module
        self.command = command
        self.detail = detail
        self.target_version = target_version


def _calc_selected_mod_names(modules=None):
    # allow user to run only on CLI or extensions
    cli_only = modules == ['CLI']
    ext_only = modules == ['EXT']
    if cli_only or ext_only:
        modules = None

    selected_modules = get_path_table(include_only=modules)

    if cli_only:
        selected_modules['ext'] = {}
    if ext_only:
        selected_modules['core'] = {}
        selected_modules['mod'] = {}

    if not any(selected_modules.values()):
        logger.warning('No commands selected to check.')

    selected_mod_names = list(selected_modules['mod'].keys())
    selected_mod_names += list(selected_modules['ext'].keys())
    selected_mod_names += list(selected_modules['core'].keys())
    return selected_mod_names


def _load_commands():
    start = time.time()
    display('Initializing with loading command table...')
    from azure.cli.core import get_default_cli  # pylint: disable=import-error
    az_cli = get_default_cli()

    # load commands, args, and help
    _create_invoker_and_load_cmds(az_cli)

    stop = time.time()
    logger.info('Commands loaded in %i sec', stop - start)
    display('Commands loaded in {} sec'.format(stop - start))
    command_loader = az_cli.invocation.commands_loader

    if not command_loader.command_table:
        logger.warning('No commands selected to check.')
    return command_loader


def _handle_custom_breaking_changes(module, command):
    """
    Collect Custom Pre-Announcement defined in `_breaking_change.py`
    :param module: module name
    :param command: command name
    :return: A generated returns Custom Pre-Announcements defined in `_breaking_change.py`
    """
    from azure.cli.core.breaking_change import upcoming_breaking_changes
    yield from _handle_custom_breaking_change(module, command, upcoming_breaking_changes.get(command))
    for key in upcoming_breaking_changes:
        if key.startswith(command + '.'):
            yield from _handle_custom_breaking_change(module, command, upcoming_breaking_changes[key])


def _handle_custom_breaking_change(module, command, breaking_change):
    """
    Handle a BreakingChange item defined in `_breaking_change.py`. We need this method because the item stored could
    be a list or object
    """
    from azure.cli.core.breaking_change import BreakingChange
    if isinstance(breaking_change, str):
        yield BreakingChangeItem(module, command, breaking_change, None)
    elif isinstance(breaking_change, BreakingChange):
        yield BreakingChangeItem(module, command, breaking_change.message, breaking_change.target_version.version())
    elif isinstance(breaking_change, list):
        for bc in breaking_change:
            yield from _handle_custom_breaking_change(module, command, bc)


def _handle_command_deprecation(module, command, deprecate_info):
    redirect = f' and replaced by `{deprecate_info.redirect}`' if deprecate_info.redirect else ''
    version = deprecate_info.expiration if hasattr(deprecate_info, "expiration") else None
    expiration = f' This command would be removed in {version}.' if version else ''
    yield BreakingChangeItem(module, command, f'This command is deprecated{redirect}.{expiration}', version)


def _calc_target_of_arg_deprecation(arg_name, arg_settings):
    from knack.deprecation import Deprecated
    option_str_list = []
    depr = arg_settings.get('deprecate_info')
    for option in arg_settings.get('option_list', []):
        if isinstance(option, str):
            option_str_list.append(option)
        elif isinstance(option, Deprecated):
            option_str_list.append(option.target)
    if option_str_list:
        return '/'.join(option_str_list)
    elif hasattr(depr, 'target'):
        return depr.target
    else:
        return arg_name


def _handle_arg_deprecation(module, command, target, deprecation_info):
    redirect = f' and replaced by `{deprecation_info.redirect}`' if deprecation_info.redirect else ''
    version = deprecation_info.expiration if hasattr(deprecation_info, "expiration") else None
    expiration = f' This parameter would be removed in {version}.' if version else ''
    yield BreakingChangeItem(module, command, f'This parameter `{target}` is deprecated{redirect}.{expiration}',
                             version)


def _handle_options_deprecation(module, command, options):
    from knack.deprecation import Deprecated
    deprecate_option_map = defaultdict(lambda: [])
    for option in options:
        if isinstance(option, Deprecated):
            key = f'{option.redirect}|{option.expiration}|{option.hide}'
            deprecate_option_map[key].append(option)
    for _, depr_list in deprecate_option_map.items():
        target = '/'.join([depr.target for depr in depr_list])
        depr = depr_list[0]
        redirect = f' and replaced by `{depr.redirect}`' if depr.redirect else ''
        version = depr.expiration if hasattr(depr, "expiration") else None
        expiration = f' This command would be removed in {version}.' if version else ''
        yield BreakingChangeItem(module, command, f'This option `{target}` is deprecated{redirect}.{expiration}',
                                 version)


def _handle_command_breaking_changes(module, command, command_info):
    if hasattr(command_info, "deprecate_info") and command_info.deprecate_info:
        yield from _handle_command_deprecation(module, command, command_info.deprecate_info)

    for argument_name, argument in command_info.arguments.items():
        arg_settings = argument.type.settings
        depr = arg_settings.get('deprecate_info')
        if depr:
            bc_target = _calc_target_of_arg_deprecation(argument_name, arg_settings)
            yield from _handle_arg_deprecation(module, command, bc_target, depr)
        yield from _handle_options_deprecation(module, command, arg_settings.get('options', []))

    yield from _handle_custom_breaking_changes(module, command)


def _handle_command_group_deprecation(module, command, deprecate_info):
    redirect = f' and replaced by `{deprecate_info.redirect}`' if deprecate_info.redirect else ''
    version = deprecate_info.expiration if hasattr(deprecate_info, "expiration") else None
    expiration = f' This command would be removed in {version}.' if version else ''
    yield BreakingChangeItem(module, command, f'This command group is deprecated{redirect}.{expiration}', version)


def _handle_command_group_breaking_changes(module, command_group_name, command_group_info):
    if hasattr(command_group_info, 'group_kwargs') and command_group_info.group_kwargs.get('deprecate_info'):
        yield from _handle_command_group_deprecation(module, command_group_name,
                                                     command_group_info.group_kwargs.get('deprecate_info'))

    yield from _handle_custom_breaking_changes(module, command_group_name)


def _get_module_name(loader):
    module_source = next(iter(loader.command_table.values())).command_source
    if isinstance(module_source, str):
        return module_source
    else:
        return module_source.extension_name


def _iter_and_prepare_module_loader(command_loader, selected_mod_names):
    for loader in command_loader.loaders:
        module_path = loader.__class__.__module__
        module_name = _get_module_name(loader)
        if module_name not in selected_mod_names:
            continue

        _breaking_change_module = f'{module_path}._breaking_change'
        try:
            import_module(_breaking_change_module)
        except ImportError:
            pass
        loader.skip_applicability = True

        yield module_name, loader


def _handle_module(module, loader, main_loader):
    start = time.time()

    for command, command_info in loader.command_table.items():
        main_loader.load_arguments(command)

        yield from _handle_command_breaking_changes(module, command, command_info)

    for command_group_name, command_group in loader.command_group_table.items():
        yield from _handle_command_group_breaking_changes(module, command_group_name, command_group)

    stop = time.time()
    logger.info('Module %s finished in %i sec', module, stop - start)
    display('Module {} finished loaded in {} sec'.format(module, stop - start))


def _handle_core():
    start = time.time()
    core_module = 'azure.cli.core'
    _breaking_change_module = f'{core_module}._breaking_change'
    try:
        import_module(_breaking_change_module)
    except ImportError:
        pass

    yield from _handle_custom_breaking_changes('core', 'core')

    stop = time.time()
    logger.info('Core finished in %i sec', stop - start)
    display('Core finished loaded in {} sec'.format(stop - start))


def _handle_upcoming_breaking_changes(selected_mod_names):
    command_loader = _load_commands()

    if 'core' in selected_mod_names or 'azure-cli-core' in selected_mod_names:
        yield from _handle_core()

    for module, loader in _iter_and_prepare_module_loader(command_loader, selected_mod_names):
        yield from _handle_module(module, loader, command_loader)


def _filter_breaking_changes(iterator, max_version=None):
    if not max_version:
        yield from iterator
        return
    try:
        parsed_max_version = packaging.version.parse(max_version)
    except packaging.version.InvalidVersion:
        logger.warning('Invalid target version: %s; '
                       'Will present all upcoming breaking changes as alternative.', max_version)
        yield from iterator
        return
    for item in iterator:
        if item.target_version:
            try:
                target_version = packaging.version.parse(item.target_version)
                if target_version <= parsed_max_version:
                    yield item
            except packaging.version.InvalidVersion:
                logger.warning('Invalid version from `%s`: %s', item.command, item.target_version)


# pylint: disable=unnecessary-lambda-assignment
def _group_breaking_change_items(iterator, group_by_version=False):
    if group_by_version:
        upcoming_breaking_changes = defaultdict(    # module to command
            lambda: defaultdict(    # command to version
                lambda: defaultdict(    # version to list of breaking changes
                    lambda: [])))
    else:
        upcoming_breaking_changes = defaultdict(    # module to command
            lambda: defaultdict(    # command to list of breaking changes
                lambda: []))
    for item in iterator:
        version = item.target_version if item.target_version else 'Unspecific'
        if group_by_version:
            upcoming_breaking_changes[item.module][item.command][version].append(item.detail)
        else:
            upcoming_breaking_changes[item.module][item.command].append(item.detail)
    return upcoming_breaking_changes


def collect_upcoming_breaking_changes(modules=None, target_version='NextWindow', group_by_version=None,
                                      output_format='structure'):
    if target_version == 'NextWindow':
        from azure.cli.core.breaking_change import NEXT_BREAKING_CHANGE_RELEASE
        target_version = NEXT_BREAKING_CHANGE_RELEASE
    elif target_version.lower() == 'none':
        target_version = None

    require_azure_cli()

    selected_mod_names = _calc_selected_mod_names(modules)

    if selected_mod_names:
        display('Modules selected: {}\n'.format(', '.join(selected_mod_names)))

    heading('Collecting Breaking Change Pre-announcement')
    breaking_changes = _handle_upcoming_breaking_changes(selected_mod_names)
    breaking_changes = _filter_breaking_changes(breaking_changes, target_version)
    breaking_changes = _group_breaking_change_items(breaking_changes, group_by_version)
    if output_format == 'structure':
        return breaking_changes
    elif output_format == 'markdown':
        from jinja2 import Environment, PackageLoader
        env = Environment(loader=PackageLoader('azdev', 'operations/breaking_change'),
                          trim_blocks=True)
        template = env.get_template('markdown_template.jinja2')
        output(template.render({'module_bc': breaking_changes}))
    return None

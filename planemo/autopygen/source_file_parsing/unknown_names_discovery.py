"""
Module containing discovery classes used to find names
(assignments to variables) that have not been extracted yet
"""
import ast
from .parsing_commons import Discovery, CustomVisitor
from typing import Tuple, List, Any, Set
import sys
import builtins


class UnknownNamesDiscovery(CustomVisitor):
    """
    Discovery class used to find names that have not been initialized yet but
    are necessary for correct argument parser init
    """

    def __init__(self, known_names: Set[str]):
        self.known_names = known_names
        self.unknown_names = set()

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id not in self.known_names:
            self.unknown_names.add(node.id)

    # def visit_For(self, node: ast.For) -> Any:
    #     for item in node.body:
    #         self.generic_visit(item)

    def visit_ListComp(self, node: ast.ListComp) -> Any:
        for comprehension in node.generators:
            if isinstance(comprehension.target, ast.Name):
                self.known_names.add(comprehension.target.id)

        self.generic_visit(node)

    def report_findings(self) -> Tuple:
        return self.unknown_names,


class UnknownNameInit(CustomVisitor):
    """
    Class used to initialize unknown names
    """

    def __init__(self, unknown_names: Set[str]):
        self.unknown_names = unknown_names
        self.class_definitions = []
        self.variable_definitions = []
        self.new_known_names = set()

    # assignment of variables
    def visit_Assign(self, node: ast.Assign) -> Any:
        target, = node.targets

        if isinstance(target, ast.Name) and target.id in self.unknown_names:
            self.variable_definitions.append(node)
            self.new_known_names.add(target.id)

    # if members of class are used, class definition has to be a
    # part of actions
    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        if node.name in self.unknown_names:
            self.class_definitions.append(node)
            self.new_known_names.add(node.name)

    def report_findings(self) -> Tuple:
        return self.variable_definitions, self.class_definitions, \
               self.new_known_names


def _insert_into_actions(actions: List[ast.AST], assignments: List[ast.Assign],
                         class_defs: List[ast.ClassDef]):
    def find_end_of_imports():
        index = 0
        for item in actions:
            if not (isinstance(item, ast.Import) or
                    isinstance(item, ast.ImportFrom)):
                return index

            index += 1

        return index

    end_of_imports = find_end_of_imports()
    if assignments:
        actions.insert(end_of_imports, *assignments)

    if class_defs:
        actions.insert(end_of_imports, *class_defs)


def initialize_variables_in_module(original_module: ast.Module,
                                   parser_name: str,
                                   sections: Set[str],
                                   actions: List[ast.AST],
                                   imported_names: Set[str]) -> \
        Tuple[List[ast.AST], Set[str]]:
    """
    Function used to initialize variables that have constant values

    Parameters
    ----------

    original_module : ast.Module
     AST of the original source file
    parser_name : str
     default name of the parser
    sections : Set[str]
     set of section names
    actions : List[ast.AST]
     list of actions extracted so far
    imported_names : Set[str]
     list of names imported from modules

    Returns
    -------
    List containing newly extracted actions and new unknown names
    """
    builtin_names = [e for e in builtins.__dict__]
    lib_modules = sys.stdlib_module_names

    # this is a set of all known names, basically the things that are already
    # known and don't have to be added to the list of actions
    known_names = {parser_name, *sections,
                   *builtin_names, *lib_modules, *imported_names}

    while True:
        unknown_names_discovery = UnknownNamesDiscovery(known_names)
        extracted_module = ast.Module(body=actions, type_ignores=[])
        unknown_names, = unknown_names_discovery.visit_and_report(
            extracted_module)

        # after unknown names initialization is complete, new known_names set is
        # created and new actions are added to the action list
        unknown_names_loader = UnknownNameInit(unknown_names)
        new_vars, new_classes, new_known_names = \
            unknown_names_loader.visit_and_report(original_module)

        _insert_into_actions(actions, new_vars, new_classes)
        known_names = known_names.union(new_known_names)

        if len(new_known_names) == 0:
            break

    return actions, unknown_names

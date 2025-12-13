#!/usr/bin/env python3
"""
Convert Pydantic models to TypeScript interfaces using AST parsing
No runtime dependencies - pure AST parsing
Full Pydantic v2 support
"""

import ast
from pathlib import Path
from typing import List, Optional, Set


class TypeScriptConverter:
    """Converts Pydantic models to TypeScript interfaces using AST parsing"""

    # Python to TypeScript type mappings
    TYPE_MAP = {
        "int": "number",
        "float": "number",
        "str": "string",
        "bool": "boolean",
        "datetime": "string",
        "date": "string",
        "time": "string",
        "UUID": "string",
        "EmailStr": "string",
        "Any": "any",
        "None": "null",
        "NoneType": "null",
    }

    def __init__(self, camel_case: bool = True, optional_fields: bool = True):
        self.camel_case = camel_case
        self.optional_fields = optional_fields
        self.imported_enums: Set[str] = set()
        self.imported_types: Set[str] = set()

    def to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to camelCase"""
        components = snake_str.split("_")
        return components[0] + "".join(x.title() for x in components[1:])

    def convert_field_name(self, name: str) -> str:
        """Convert field name based on naming convention"""
        if self.camel_case:
            return self.to_camel_case(name)
        return name

    def convert_type(self, annotation: ast.expr) -> str:
        """Convert Python type annotation to TypeScript type"""
        if isinstance(annotation, ast.Name):
            # Simple type: int, str, bool, etc.
            type_name = annotation.id
            return self.TYPE_MAP.get(type_name, type_name)

        elif isinstance(annotation, ast.Constant):
            # Literal type
            if annotation.value is None:
                return "null"
            return f'"{annotation.value}"'

        elif isinstance(annotation, ast.Subscript):
            # Generic types: list[T], dict[K, V], Optional[T], Union[A, B]
            value = annotation.value

            if isinstance(value, ast.Name):
                if value.id == "list":
                    # list[T] -> T[]
                    inner_type = self.convert_type(annotation.slice)
                    return f"{inner_type}[]"
                elif value.id == "List":
                    # List[T] -> T[]
                    inner_type = self.convert_type(annotation.slice)
                    return f"{inner_type}[]"
                elif value.id == "dict":
                    # dict[K, V] -> Record<K, V>
                    if isinstance(annotation.slice, ast.Tuple):
                        key_type = self.convert_type(annotation.slice.elts[0])
                        val_type = self.convert_type(annotation.slice.elts[1])
                        return f"Record<{key_type}, {val_type}>"
                    return "Record<string, any>"
                elif value.id == "Dict":
                    # Dict[K, V] -> Record<K, V>
                    if isinstance(annotation.slice, ast.Tuple):
                        key_type = self.convert_type(annotation.slice.elts[0])
                        val_type = self.convert_type(annotation.slice.elts[1])
                        return f"Record<{key_type}, {val_type}>"
                    return "Record<string, any>"
                elif value.id == "Optional":
                    # Optional[T] -> T | null
                    inner_type = self.convert_type(annotation.slice)
                    return f"{inner_type} | null"
                elif value.id == "Union":
                    # Union[A, B] -> A | B
                    if isinstance(annotation.slice, ast.Tuple):
                        types = [self.convert_type(t) for t in annotation.slice.elts]
                        return " | ".join(types)
                    return "any"

            elif isinstance(value, ast.Attribute):
                # Something like typing.Optional
                if value.attr == "Optional":
                    inner_type = self.convert_type(annotation.slice)
                    return f"{inner_type} | null"

        elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            # Python 3.10+ union syntax: str | None
            left = self.convert_type(annotation.left)
            right = self.convert_type(annotation.right)
            return f"{left} | {right}"

        elif isinstance(annotation, ast.Attribute):
            # Qualified name: datetime.datetime, uuid.UUID
            if annotation.attr in self.TYPE_MAP:
                return self.TYPE_MAP[annotation.attr]
            # Enum or custom type
            type_name = annotation.attr
            self.imported_types.add(type_name)
            return type_name

        return "any"

    def extract_field_info(self, node: ast.AnnAssign) -> tuple[str, str, bool]:
        """Extract field name, type, and optional status from annotation assignment"""
        if not isinstance(node.target, ast.Name):
            return None, None, False

        field_name = node.target.id
        ts_field_name = self.convert_field_name(field_name)

        # Get type annotation
        if node.annotation:
            ts_type = self.convert_type(node.annotation)
        else:
            ts_type = "any"

        # Check if optional (has default value or is Optional/Union with None)
        is_optional = False
        if node.annotation:
            # Check if type is Optional or Union with None
            if isinstance(node.annotation, ast.Subscript):
                if isinstance(node.annotation.value, ast.Name):
                    if node.annotation.value.id in ("Optional", "Union"):
                        is_optional = True
            elif isinstance(node.annotation, ast.BinOp):
                # str | None syntax
                is_optional = True

        # If has default value and type is not already optional, make it optional
        if node.value is not None and not is_optional:
            # Check if default is None
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                is_optional = True
            # Check for None default (Python 3.8+ uses ast.Constant, older uses ast.NameConstant)
            try:
                if hasattr(node.value, "value") and node.value.value is None:
                    is_optional = True
            except Exception:
                pass

        return ts_field_name, ts_type, is_optional

    def extract_class_docstring(self, node: ast.ClassDef) -> Optional[str]:
        """Extract docstring from class"""
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            return node.body[0].value.value
        return None

    def convert_class(self, node: ast.ClassDef) -> str:
        """Convert a Pydantic BaseModel class to TypeScript interface"""
        lines = []

        # Extract docstring
        docstring = self.extract_class_docstring(node)
        if docstring:
            # Clean up docstring (remove extra whitespace)
            doc_clean = " ".join(docstring.split())
            lines.append(f"  /** {doc_clean} */")

        # Extract fields
        fields = []
        for item in node.body:
            # Skip model_config
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "model_config":
                        continue

            if isinstance(item, ast.AnnAssign):
                field_name, field_type, is_optional = self.extract_field_info(item)
                if field_name and field_type:
                    optional_marker = "?" if (is_optional and self.optional_fields) else ""
                    fields.append(f"  {field_name}{optional_marker}: {field_type};")

        # Only generate if we have fields
        if not fields:
            return ""

        # Generate interface
        interface_name = node.name
        lines.append(f"export interface {interface_name} {{")
        lines.extend(fields)
        lines.append("}")

        return "\n".join(lines)

    def extract_enum(self, node: ast.ClassDef) -> Optional[str]:
        """Extract Enum class and convert to TypeScript enum"""
        # Check if it inherits from Enum (can be Enum, PyEnum, or str, PyEnum)
        is_enum = False
        for base in node.bases:
            if isinstance(base, ast.Name):
                if base.id in ("Enum", "PyEnum"):
                    is_enum = True
                    break
            elif isinstance(base, ast.Attribute):
                if base.attr in ("Enum", "PyEnum"):
                    is_enum = True
                    break
            elif isinstance(base, ast.Tuple):
                # Handle (str, PyEnum) syntax
                for elt in base.elts:
                    if isinstance(elt, ast.Name) and elt.id in ("Enum", "PyEnum"):
                        is_enum = True
                        break
                if is_enum:
                    break

        if not is_enum:
            return None

        lines = []
        enum_name = node.name
        self.imported_enums.add(enum_name)

        # Extract enum values
        values = []
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        key = target.id
                        if isinstance(item.value, ast.Constant):
                            value = item.value.value
                            values.append(f'  {key} = "{value}",')

        if values:
            lines.append(f"export enum {enum_name} {{")
            lines.extend(values)
            lines.append("}")

        return "\n".join(lines) if values else None

    def convert_file(self, file_path: Path) -> tuple[str, List[str]]:
        """Convert a Python file containing Pydantic models to TypeScript"""
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=str(file_path))

        interfaces = []
        enums = []
        imports = []

        # Extract imports to understand enum/type sources
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        if alias.asname:
                            imports.append(f"import {{ {alias.name} as {alias.asname} }} from '{node.module}';")
                        else:
                            imports.append(f"import {{ {alias.name} }} from '{node.module}';")

        # First pass: collect all classes to check inheritance
        all_classes: dict[str, ast.ClassDef] = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                all_classes[node.name] = node

        def is_pydantic_class(class_name: str, visited: set[str] = None) -> bool:
            """Recursively check if a class is a Pydantic model"""
            if visited is None:
                visited = set()
            if class_name in visited:
                return False  # Prevent infinite loops
            visited.add(class_name)

            if class_name not in all_classes:
                return False

            node = all_classes[class_name]
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_name = base.id
                    if base_name == "BaseModel":
                        return True
                    # Recursively check base class
                    if is_pydantic_class(base_name, visited.copy()):
                        return True
                elif isinstance(base, ast.Attribute):
                    if base.attr == "BaseModel":
                        return True
            return False

        # Convert classes
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                # Check if it's a Pydantic model
                is_pydantic = is_pydantic_class(node.name)

                if is_pydantic:
                    interface = self.convert_class(node)
                    if interface:
                        interfaces.append(interface)
                else:
                    # Try to extract as enum
                    enum = self.extract_enum(node)
                    if enum:
                        enums.append(enum)

        # Combine all output
        output = []
        if enums:
            output.extend(enums)
            output.append("")
        if interfaces:
            output.extend(interfaces)

        return "\n".join(output), list(self.imported_enums | self.imported_types)

    def extract_enums_from_models(self, models_dir: Path) -> List[str]:
        """Extract enum definitions from model files"""
        enums = []
        seen_enums: Set[str] = set()

        # Process model files to find enums
        for model_file in sorted(models_dir.glob("*.py")):
            if model_file.name == "__init__.py":
                continue

            with open(model_file, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=str(model_file))

            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    enum_def = self.extract_enum(node)
                    if enum_def:
                        enum_name = enum_def.split()[2].split("{")[0]
                        if enum_name not in seen_enums:
                            enums.append(enum_def)
                            seen_enums.add(enum_name)

        return enums

    def convert_directory(self, input_dir: Path, output_file: Path, models_dir: Path = None) -> None:
        """Convert all Python files in a directory to a single TypeScript file"""
        all_interfaces = []
        all_enums = []
        seen_enums: Set[str] = set()
        seen_interfaces: Set[str] = set()

        # Extract enums from model files if models_dir provided
        if models_dir and models_dir.exists():
            print(f"📦 Extracting enums from models: {models_dir}")
            model_enums = self.extract_enums_from_models(models_dir)
            for enum_def in model_enums:
                enum_name = enum_def.split()[2].split("{")[0]
                if enum_name not in seen_enums:
                    all_enums.append(enum_def)
                    seen_enums.add(enum_name)

        # Process all Python files in schemas
        for py_file in sorted(input_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue

            print(f"📄 Processing: {py_file.name}")
            content, imports = self.convert_file(py_file)
            if content:
                # Split by "export " to get individual interfaces/enums
                # Each export statement starts a new interface/enum
                parts = []
                current_part: list[str] = []
                for line in content.split("\n"):
                    if line.strip().startswith("export "):
                        if current_part:
                            parts.append("\n".join(current_part))
                        current_part = [line]
                    elif current_part:
                        current_part.append(line)
                if current_part:
                    parts.append("\n".join(current_part))

                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    if part.startswith("export enum"):
                        enum_name = part.split()[2].split("{")[0]
                        if enum_name not in seen_enums:
                            all_enums.append(part)
                            seen_enums.add(enum_name)
                    elif part.startswith("export interface"):
                        # Extract interface name
                        interface_name = part.split()[2].split("{")[0]
                        if interface_name not in seen_interfaces:
                            all_interfaces.append(part)
                            seen_interfaces.add(interface_name)

        # Combine output
        output_lines = [
            "/**",
            " * TypeScript types generated from Pydantic models",
            " * Auto-generated - DO NOT EDIT MANUALLY",
            " * Generated from: sumii-mobile-api/app/schemas/",
            " */",
            "",
        ]

        if all_enums:
            output_lines.extend(all_enums)
            output_lines.append("")

        if all_interfaces:
            output_lines.extend(all_interfaces)

        # Write output
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines))

        print(f"✅ Generated {len(all_interfaces)} interfaces and {len(all_enums)} enums")
        print(f"📄 Output: {output_file}")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Convert Pydantic models to TypeScript interfaces")
    parser.add_argument("--input", "-i", required=True, help="Input Python file or directory")
    parser.add_argument("--output", "-o", required=True, help="Output TypeScript file")
    parser.add_argument("--models", "-m", help="Models directory to extract enums from (optional)")
    parser.add_argument("--camel-case", action="store_true", default=True, help="Convert to camelCase (default: True)")
    parser.add_argument("--no-camel-case", dest="camel_case", action="store_false", help="Keep snake_case")
    parser.add_argument(
        "--optional", action="store_true", default=True, help="Mark optional fields with ? (default: True)"
    )

    args = parser.parse_args()

    converter = TypeScriptConverter(camel_case=args.camel_case, optional_fields=args.optional)

    input_path = Path(args.input)
    output_path = Path(args.output)
    models_path = Path(args.models) if args.models else None

    if input_path.is_file():
        content, _ = converter.convert_file(input_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Generated TypeScript types: {output_path}")
    elif input_path.is_dir():
        converter.convert_directory(input_path, output_path, models_dir=models_path)
    else:
        print(f"❌ Error: {input_path} is not a file or directory")
        exit(1)


if __name__ == "__main__":
    main()

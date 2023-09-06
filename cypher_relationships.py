import re


PATTERN_CONFIG = {
    "node1_pattern": r"""(?P<node1>
                                        \(                                   # Required left node boundary
                                        (?P<node1_var_name>[a-zA-Z0-9_]*)    # Optional variable name
                                        (?P<node1_labels>[:!a-zA-Z0-9_`]*)   # Optional multiple or negated node labels
                                        \s*(?P<node1_props>\{.*?\})*         # Optional node properties specification
                                        \)                                   # Required right node boundary
                                       )                                  
                                   """,
    "arrow_pattern": r"""(?P<rel>
                                        (?P<rel_left_arrow><)?              # Optional left arrowhead
                                        \-                                  # Required left relationship hyphen
                                        \[?                                 # Optional left bracket
                                        (?P<rel_var_name>[a-zA-Z0-9_]*)     # Optional variable name
                                        (?P<rel_labels>[:!a-zA-Z0-9_|`]*)   # Optional relationship labels
                                        \s*(?P<rel_props>\{.*?\})*          # Optional relationship properties spec
                                        (?P<rel_hops>\*?[.0-9]*)            # Optional multiple hops spec
                                        \]?                                 # Optional right bracket
                                        \-                                  # Required right relationship hyphen
                                        (?P<rel_right_arrow>>)?             # Optional right arrowhead
                                       )
                                   """,
    "node2_pattern": r"""(?P<node2> 
                                        \(                                   # Required left node boundary
                                        (?P<node2_var_name>[a-zA-Z0-9_]*)    # Optional variable name
                                        (?P<node2_labels>[:!a-zA-Z0-9_`]*)   # Optional multiple or negated node labels
                                        \s*(?P<node2_props>\{.*?\})*         # Optional node properties specification
                                        \)                                   # Required right node boundary
                                        )                                  
                                   """,
}


def fix_cypher_relationship_directions(
    cypher_text, schema_text, pattern_config=PATTERN_CONFIG
):
    """
    Corrects relationship direction in the text of Cypher queries when provided a schema in the proper format.

    See the examples for proper formatting of inputs. Schema must be provided as a single string with comma-
    separated triples enclosed in parentheses.

    Originally written as a submission to this contest:
    https://github.com/tomasonjo/cypher-direction-competition
    Full details of validation dataset and business rules applied can be found at this link.

    Args:
        cyper_text (str): The text of a valid Cypher query
        schema_text (str): Text containing triples that define possible relationships in database schema
        pattern_config (dict): Dictionary that defines regex patterns for the parts of a cypher relationship

    Returns:
        str: The text of the Cypher query with relationship directions corrected according to the provided schema.

    Examples:
        >>> cypher_text = "MATCH (p:Person) RETURN p, [(p)<-[:WORKS_AT]-(o:Organization) | o.name] AS op"
        >>> schema_text = "(Person, KNOWS, Person), (Person, WORKS_AT, Organization)"
        >>> fix_cypher_relationship_directions(cypher_text, schema_text)
        'MATCH (p:Person) RETURN p, [(p)-[:WORKS_AT]->(o:Organization) | o.name] AS op'
    """
    # Process schema to be list of tuples.
    schema_lst = process_schema(schema_text)

    # Use regular expressions (re library) to detect relationship patterns and return as list of dicts.
    relationships = detect_relationships(cypher_text, schema_lst, pattern_config)

    for rel in relationships:
        # Check if relationship exists within the defined schema.
        find_relationship_in_schema(rel, schema_lst)

        # Check for schema mismatches and return empty string if present.
        if "schema_match" in rel and rel["schema_match"] == False:
            cypher_text = ""
            break

        # Correct incorrect directions.
        if "is_correct" in rel and not rel["is_correct"]:
            cypher_text = switch_direction(cypher_text, rel)

    return cypher_text


def process_schema(schema_text):
    # Takes schema in the form "(Person, KNOWS, Person), (Person, WORKS_AT, Organization)" and returns parsed list of tuples.
    schema_lst = [
        tuple(item.split(","))
        for item in schema_text.replace(" ", "").lstrip("(").rstrip(")").split("),(")
    ]
    return schema_lst


def detect_relationships(cypher_text, schema_lst, pattern_config):
    # Establish regex patterns for relationship and identify matching relationships.
    relationship_pattern_text = (
        r"(?=(?P<whole_relationship>"
        + pattern_config["node1_pattern"]
        + pattern_config["arrow_pattern"]
        + pattern_config["node2_pattern"]
        + r"))"
    )
    relationship_pattern = re.compile(relationship_pattern_text, re.VERBOSE)

    relationships = [
        {"object": r} for r in re.finditer(relationship_pattern, cypher_text)
    ]

    for rel in relationships:
        # Propogate node labels from prior variable definitions if available
        detect_node_labels(rel, cypher_text, pattern_config)

        # Define the characteristics of the relationship that we can use to apply rules for deciding whether and how to change relationship directions.
        detect_relationship_characteristics(rel)

        # Convert any relationship with a negated label into its positive, multi_label form
        if rel["is_negated_label"]:
            transform_negated_to_multi_label(rel, schema_lst)

    return relationships


def detect_node_labels(relationship, cypher_text, pattern_config):
    # Define variable names for nodes set labels to FIRST available label if defined.
    relationship["node1"] = {
        "var_name": relationship["object"].group("node1_var_name"),
        "label1": next(
            iter(
                relationship["object"]
                .group("node1_labels")
                .lstrip(":")
                .replace("`", "")
                .split(":")
                or [""]
            )
        ),
    }
    relationship["node2"] = {
        "var_name": relationship["object"].group("node2_var_name"),
        "label1": next(
            iter(
                relationship["object"]
                .group("node2_labels")
                .lstrip(":")
                .replace("`", "")
                .split(":")
                or [""]
            )
        ),
    }

    # Detect FIRST node label for all nodes present in the Cypher query.
    node_label_map = {
        node.group("node1_var_name"): next(
            iter(
                node.group("node1_labels").lstrip(":").replace("`", "").split(":")
                or [""]
            )
        )
        for node in re.finditer(
            re.compile(pattern_config["node1_pattern"], re.VERBOSE), cypher_text
        )
        if node.group("node1_labels")
    }

    # Propogate node labels from the original variable definition to nodes in the relationship definition.
    if relationship["node1"]["label1"] == "":
        relationship["node1"]["label1"] = node_label_map.get(
            relationship["node1"]["var_name"], ""
        )
    if relationship["node2"]["label1"] == "":
        relationship["node2"]["label1"] = node_label_map.get(
            relationship["node2"]["var_name"], ""
        )


def detect_relationship_characteristics(relationship):
    # Tuple containing labels for nodes and relationships.  Nodes have FIRST label only.  Relationships have all labels with original separator.
    relationship["tup"] = (
        relationship["node1"]["label1"].strip("`"),
        relationship["object"].group("rel_labels").lstrip(":").replace("`", ""),
        relationship["node2"]["label1"].strip("`"),
    )

    # Relationship direction should be '<', '>', or None.
    relationship["direction"] = relationship["object"].group(
        "rel_left_arrow"
    ) or relationship["object"].group("rel_right_arrow")

    # Tests if node labels are equivalent.
    relationship["node_labels_same"] = (
        relationship["node1"]["label1"] == relationship["node2"]["label1"]
    )

    # Tests if relationship could have variable length such as '*' or '*1..4' characters following relationship label.
    relationship["is_variable_length"] = (
        relationship["object"].group("rel_hops") == "*"
    ) or (
        "*" in relationship["object"].group("rel_hops")
        and ".." in relationship["object"].group("rel_hops")
    )

    # Tests for presence of pipe character which implies that the relationship has multiple labels.
    relationship["is_multi_label"] = "|" in str(
        relationship["object"].group("rel_labels")
    )

    # Extracts a list of all relationship labels detected.
    relationship["multi_labels"] = [
        re.sub(r"[\s`:]*", r"", label)
        for label in relationship["object"].group("rel_labels").split("|")
    ]

    # Tests for presence of '!' which implies that the relationship type is negated.
    relationship["is_negated_label"] = (
        relationship["object"].group("rel_labels").lstrip(":").startswith("!")
    )


def transform_negated_to_multi_label(relationship, schema_lst):
    # Treat negated label as multi-labeled relationship so that we can detect if ANY implied relationship label fits the schema.
    negated_label = relationship["tup"][1].lstrip("!")
    relationship["multi_labels"] = [
        item[1] for item in schema_lst if item[1] != negated_label
    ]
    relationship["is_multi_label"] = True


def find_relationship_in_schema(relationship, schema_lst):
    for label in relationship["multi_labels"]:
        # Overwrite the relationship tuple definition to be for single label case so we can try to find one relationship at a time.
        relationship["tup"] = (
            relationship["node1"]["label1"],
            label,
            relationship["node2"]["label1"],
        )
        find_single_label_relationship_in_schema(relationship, schema_lst)

        # If any correct relationship direction is found, stop looking because we will not correct relationship direction.
        if relationship.get("is_correct", False) == True:
            break


def find_single_label_relationship_in_schema(relationship, schema_lst):
    # Don't do anything further if relationship is undirected, between two nodes of same label, or is of variable length.
    if is_unfixable(relationship):
        relationship["is_correct"] = True
        relationship["schema_match"] = True

    # If all relationship labels and types exist, try to find it in schema.
    elif is_complete(relationship):
        find_complete_tup_in_schema(relationship, schema_lst)

    # If not all relationship labels and types exist, delegate to partial match function.
    else:
        find_partial_tup_in_schema(relationship, schema_lst)


def find_complete_tup_in_schema(relationship, schema_lst):
    # If the current direction of the relationship is correct, mark it as such.
    if make_left_to_right(relationship) in schema_lst:
        relationship["is_correct"] = True
        relationship["schema_match"] = True
    # If the reverse direction of the relationship is found in schema, mark it as incorrect.
    elif make_left_to_right(relationship)[::-1] in schema_lst:
        relationship["is_correct"] = False
        relationship["schema_match"] = True
    # If the relationship is not found at all, mark 'schema_match' as False so we can know to return an empty string.
    else:
        relationship["schema_match"] = False


def find_partial_tup_in_schema(relationship, schema_lst):
    left_to_right_relationship = make_left_to_right(relationship)
    pieces_existing = tuple(bool(item) for item in left_to_right_relationship)

    # With one node label and one relationship label, the schema can still be checked for any correct relationship.
    if pieces_existing == (True, True, False):
        if left_to_right_relationship[:2] in zip(
            [item[0] for item in schema_lst], [item[1] for item in schema_lst]
        ):
            relationship["is_correct"] = True
            relationship["schema_match"] = True
        elif left_to_right_relationship[:2] in zip(
            [item[2] for item in schema_lst], [item[1] for item in schema_lst]
        ):
            relationship["is_correct"] = False
            relationship["schema_match"] = True
        else:
            relationship["schema_match"] = False

    # With one node label and one relationship label, the schema can still be checked for any correct relationship.
    elif pieces_existing == (False, True, True):
        if left_to_right_relationship[1:] in zip(
            [item[1] for item in schema_lst], [item[2] for item in schema_lst]
        ):
            relationship["is_correct"] = True
            relationship["schema_match"] = True
        elif left_to_right_relationship[1:] in zip(
            [item[1] for item in schema_lst], [item[0] for item in schema_lst]
        ):
            relationship["is_correct"] = False
            relationship["schema_match"] = True
        else:
            relationship["schema_match"] = False

    # With two node labels, the schema can still be checked for any potentially matching relationship.
    elif pieces_existing == (True, False, True):
        if tuple([left_to_right_relationship[0], left_to_right_relationship[2]]) in zip(
            [item[0] for item in schema_lst], [item[2] for item in schema_lst]
        ):
            relationship["is_correct"] = True
            relationship["schema_match"] = True
        elif tuple(
            [left_to_right_relationship[0], left_to_right_relationship[2]]
        ) in zip([item[2] for item in schema_lst], [item[0] for item in schema_lst]):
            relationship["is_correct"] = False
            relationship["schema_match"] = True
        else:
            relationship["schema_match"] = False

    # With one node label, the schema can still be checked for any potentially matching relationship.
    elif pieces_existing == (True, False, False):
        if left_to_right_relationship[0] in [item[0] for item in schema_lst]:
            relationship["is_correct"] = True
            relationship["schema_match"] = True
        elif left_to_right_relationship[0] in [item[2] for item in schema_lst]:
            relationship["is_correct"] = False
            relationship["schema_match"] = True
        else:
            relationship["schema_match"] = False

    # With one node label, the schema can still be checked for any potentially matching relationship.
    elif pieces_existing == (False, False, True):
        if left_to_right_relationship[2] in [item[2] for item in schema_lst]:
            relationship["is_correct"] = True
            relationship["schema_match"] = True
        elif left_to_right_relationship[2] in [item[0] for item in schema_lst]:
            relationship["is_correct"] = False
            relationship["schema_match"] = True
        else:
            relationship["schema_match"] = False

    # With only a relationship label, the schema can be checked for any matching relationship label.
    elif pieces_existing == (False, True, False):
        if left_to_right_relationship[1] in [item[1] for item in schema_lst]:
            relationship["is_correct"] = True
            relationship["schema_match"] = True
        else:
            relationship["schema_match"] = False

    # With no labels, the relationship direction is assumed to be correct.
    else:
        relationship["is_correct"] = True
        relationship["schema_match"] = True


def make_left_to_right(relationship):
    # Change tup of node and relationship labels to read left to right according to the actual direction of the relationship.
    if relationship["direction"] == "<":
        return relationship["tup"][::-1]
    else:
        return relationship["tup"]


def is_unfixable(relationship):
    # All relationships that are undirected, variable length or between nodes with the same label do not need direction changes.
    if any(
        [
            not relationship["direction"],
            relationship["node1"]["label1"] == relationship["node2"]["label1"],
            relationship["is_variable_length"],
        ]
    ):
        return True
    else:
        return False


def is_complete(relationship):
    # Test if nodes and relationship all have labels.
    if any(i == "" for i in relationship["tup"]):
        return False
    else:
        return True


def switch_direction(cypher_text, relationship):
    # Switch the direction of the given relationship within the text of the cypher query.
    old_relationship = relationship["object"].group("whole_relationship")

    if relationship["direction"] == ">":
        new_relationship = old_relationship.replace("->", "-").replace(")-", ")<-")

    elif relationship["direction"] == "<":
        new_relationship = old_relationship.replace("<-", "-").replace("-(", "->(")

    return cypher_text.replace(old_relationship, new_relationship)

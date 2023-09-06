# Cypher direction validation competition entry
This repo holds my entry for [Tomaz Bratanic's competition](https://github.com/tomasonjo/cypher-direction-competition) on validating relationship directions in Cypher queries.  

The code is structured to be imported and used as a single function that takes properly formatted Cypher query text and schema text as inputs and returns a corrected query or an empty string if a relationship does not fit the schema.  

The current version does not attempt to correct any other formatting mistakes or parse otherwise incorrectly formatted Cypher queries, since these are not requirements of the competition rules.  These features could be added in the future, however.

# Usage

```
>>> cypher_text = "MATCH (p:Person) RETURN p, [(p)<-[:WORKS_AT]-(o:Organization) | o.name] AS op"
>>> schema_text = "(Person, KNOWS, Person), (Person, WORKS_AT, Organization)"
>>> fix_cypher_relationship_directions(cypher_text, schema_text)
'MATCH (p:Person) RETURN p, [(p)-[:WORKS_AT]->(o:Organization) | o.name] AS op'
```

The `fix_cypher_relationship_directions()` function also accepts an optional `pattern_config` argument that can be used to change the regular expression specification should it be found to require modifications for specific query formats.

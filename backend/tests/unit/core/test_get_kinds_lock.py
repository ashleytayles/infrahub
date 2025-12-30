from copy import deepcopy
from typing import Any
from unittest.mock import patch

from infrahub import lock
from infrahub.core import registry
from infrahub.core.constants import BranchSupportType
from infrahub.core.constants.infrahubkind import GRAPHQLQUERY, GRAPHQLQUERYGROUP
from infrahub.core.initialization import create_branch
from infrahub.core.node.lock_utils import (
    RELATIONSHIP_COUNT_LOCK_NAMESPACE,
    _get_kinds_to_lock_on_object_mutation,
    _hash,
    get_lock_names_on_object_mutation,
)
from infrahub.core.schema import SchemaRoot
from infrahub.database import InfrahubDatabase
from tests.helpers.test_app import TestInfrahubApp
from tests.node_creation import create_and_save


class TestGetKindsLock(TestInfrahubApp):
    async def test_get_kinds_lock(
        self,
        db: InfrahubDatabase,
        default_branch,
        register_core_models_schema,
        client,
    ) -> None:
        # CoreCredential has no uniqueness_constraint, but generic CorePasswordCredential has one
        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)
        assert _get_kinds_to_lock_on_object_mutation(kind="CorePasswordCredential", schema_branch=schema_branch) == [
            "CoreCredential"
        ]

        # 3 generics but only GenericAccount has a uniqueness_constraint
        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)
        assert _get_kinds_to_lock_on_object_mutation(kind="CoreAccount", schema_branch=schema_branch) == [
            "CoreGenericAccount"
        ]

        # No uniqueness_constraint, no generic
        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)
        assert _get_kinds_to_lock_on_object_mutation(kind="BuiltinIPPrefix", schema_branch=schema_branch) == []

    async def test_lock_core_graphql_query_groups(
        self,
        db: InfrahubDatabase,
        default_branch,
        register_core_models_schema,
        client,
    ) -> None:
        graphql_query = await client.create(
            kind=GRAPHQLQUERY,
            name="a_gql_query",
            query="""mutation MyMutation {
                        InfrahubAccountTokenDelete(data: {id: "%s"}) {
                            ok
                        }
                    }""",
        )
        await graphql_query.save()

        # Test create
        with patch("infrahub.core.node.create.InfrahubMultiLock") as mock_infrahub_multi_lock:
            group = await client.create(kind=GRAPHQLQUERYGROUP, name="a_gql_group", query=graphql_query)
            await group.save()
            mock_infrahub_multi_lock.assert_called_once_with(
                lock_registry=lock.registry, locks=["global.object.CoreGroup." + _hash("a_gql_group")], metrics=False
            )

        # Test upsert the same node
        with patch("infrahub.graphql.mutations.main.InfrahubMultiLock") as mock_infrahub_multi_lock:
            group = await client.create(kind=GRAPHQLQUERYGROUP, name="a_gql_group", query=graphql_query)
            await group.save(allow_upsert=True)

            mock_infrahub_multi_lock.assert_called_with(
                lock_registry=lock.registry, locks=["global.object.CoreGroup." + _hash("a_gql_group")], metrics=False
            )

        # Test updating group name
        with patch("infrahub.graphql.mutations.main.InfrahubMultiLock") as mock_infrahub_multi_lock:
            group.name = "new_group_name"
            await group.save()

            mock_infrahub_multi_lock.assert_called_once_with(
                lock_registry=lock.registry, locks=["global.object.CoreGroup." + _hash("new_group_name")], metrics=False
            )

        # Test updating other field not present in uniqueness constraint
        # FIXME: not implemented yet
        # with patch("infrahub.graphql.mutations.main.InfrahubMultiLock") as mock_infrahub_multi_lock:
        #     query = (
        #         """mutation {
        #         CoreGraphQLQueryGroupUpdate(
        #             data: {
        #                 id: "%s"
        #                 label: { value: "new_label"}
        #             }
        #         ){
        #             ok
        #         }
        #     }
        #     """
        #         % group.id
        #     )

        #     result = await client.execute_graphql(query=query)
        #     assert result["CoreGraphQLQueryGroupUpdate"]["ok"] is True

        #     mock_infrahub_multi_lock.assert_called_once_with(lock_registry=lock.registry, locks=[], metrics=False)

        # Test lock onanother branch
        other_branch = await create_branch(branch_name="other_branch", db=db)
        with patch("infrahub.core.node.create.InfrahubMultiLock") as mock_infrahub_multi_lock:
            group = await client.create(
                kind=GRAPHQLQUERYGROUP, name="one_more_group", query=graphql_query, branch=other_branch.name
            )
            await group.save()
            mock_infrahub_multi_lock.assert_called_once_with(
                lock_registry=lock.registry, locks=["global.object.CoreGroup." + _hash("one_more_group")], metrics=False
            )

    async def test_lock_other_branch(
        self,
        db: InfrahubDatabase,
        default_branch,
        client,
        car_person_schema,
    ) -> None:
        other_branch = await create_branch(branch_name="other_branch", db=db)
        schema_branch = registry.schema.get_schema_branch(name=other_branch.name)

        person = await create_and_save(db=db, schema="TestPerson", name="John", branch=other_branch)
        assert get_lock_names_on_object_mutation(person, schema_branch=schema_branch) == [
            "global.object.TestPerson." + _hash("John")
        ]

    async def test_lock_names_only_attributes(
        self,
        db: InfrahubDatabase,
        default_branch,
        client,
        car_person_schema_unregistered,
    ) -> None:
        car_person_schema_unregistered = deepcopy(car_person_schema_unregistered)
        car_person_schema_unregistered.nodes[0].uniqueness_constraints = [
            ["name__value", "color__value", "owner__name"]
        ]
        registry.schema.register_schema(schema=car_person_schema_unregistered, branch=default_branch.name)

        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)
        person = await create_and_save(db=db, schema="TestPerson", name="John")
        car = await create_and_save(db=db, schema="TestCar", name="mercedes", color="blue", owner=person)
        assert get_lock_names_on_object_mutation(car, schema_branch=schema_branch) == [
            "global.object.TestCar." + _hash("mercedes") + "." + _hash("blue")
        ]

    async def test_lock_names_optional_empty_attribute(
        self,
        db: InfrahubDatabase,
        default_branch,
        client,
        car_person_schema_unregistered,
    ) -> None:
        car_person_schema_unregistered = deepcopy(car_person_schema_unregistered)
        car_person_schema_unregistered.nodes[1].uniqueness_constraints = [["height__value"]]
        registry.schema.register_schema(schema=car_person_schema_unregistered, branch=default_branch.name)

        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)
        person = await create_and_save(db=db, schema="TestPerson", name="John")
        assert get_lock_names_on_object_mutation(person, schema_branch=schema_branch) == [
            "global.object.TestPerson." + _hash("") + "." + _hash("John")
        ]

    async def test_lock_names_cardinality_one_relationship(
        self,
        db: InfrahubDatabase,
        default_branch,
        client,
        node_group_schema,
        data_schema,
    ) -> None:
        """Test that we add locks for relationships where the peer has cardinality one."""
        # Create a schema where:
        # - Interface has a many relationship to IPAddress
        # - IPAddress has a one relationship back to Interface (cardinality one constraint)
        schema: dict[str, Any] = {
            "nodes": [
                {
                    "name": "Interface",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "ip_address",
                            "peer": "TestIPAddress",
                            "cardinality": "many",
                            "identifier": "interface__ip_address",
                        },
                    ],
                },
                {
                    "name": "IPAddress",
                    "namespace": "Test",
                    "default_filter": "address__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "address", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "interface",
                            "peer": "TestInterface",
                            "cardinality": "one",
                            "identifier": "interface__ip_address",
                            "optional": True,
                        },
                    ],
                },
            ],
        }
        schema_root = SchemaRoot(**schema)
        registry.schema.register_schema(schema=schema_root, branch=default_branch.name)
        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)

        # Create an IP address
        ip_address = await create_and_save(db=db, schema="TestIPAddress", address="10.0.0.1/24")

        # Create an interface linked to that IP address
        interface = await create_and_save(db=db, schema="TestInterface", name="eth0", ip_address=ip_address)

        # The lock names should include the relationship_count lock for the IP address
        lock_names = get_lock_names_on_object_mutation(interface, schema_branch=schema_branch)

        expected_lock = f"{RELATIONSHIP_COUNT_LOCK_NAMESPACE}.interface__ip_address.{ip_address.id}"
        assert expected_lock in lock_names

    async def test_lock_names_direct_cardinality_one_relationship(
        self,
        db: InfrahubDatabase,
        default_branch,
        client,
        node_group_schema,
        data_schema,
    ) -> None:
        """Test that we add locks for direct cardinality one relationships on the node side."""
        # Create a schema where:
        # - Device has a cardinality one relationship to PrimaryInterface
        # - PrimaryInterface has a many relationship back to Device
        # This tests the case where the node being created has a cardinality one relationship
        schema: dict[str, Any] = {
            "nodes": [
                {
                    "name": "Device",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "primary_interface",
                            "peer": "TestPrimaryInterface",
                            "cardinality": "one",
                            "identifier": "device__primary_interface",
                            "optional": True,
                        },
                    ],
                },
                {
                    "name": "PrimaryInterface",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "devices",
                            "peer": "TestDevice",
                            "cardinality": "many",
                            "identifier": "device__primary_interface",
                        },
                    ],
                },
            ],
        }
        schema_root = SchemaRoot(**schema)
        registry.schema.register_schema(schema=schema_root, branch=default_branch.name)
        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)

        # Create a primary interface
        primary_interface = await create_and_save(db=db, schema="TestPrimaryInterface", name="eth0")

        # Create a device linked to that primary interface
        device = await create_and_save(db=db, schema="TestDevice", name="router1", primary_interface=primary_interface)

        # The lock names should include the relationship_count lock for the device's node ID
        # (not the peer's ID, since we're locking on the node's cardinality one relationship)
        lock_names = get_lock_names_on_object_mutation(device, schema_branch=schema_branch)

        expected_lock = f"{RELATIONSHIP_COUNT_LOCK_NAMESPACE}.device__primary_interface.{device.id}"
        assert expected_lock in lock_names

    async def test_lock_names_max_count_relationship(
        self,
        db: InfrahubDatabase,
        default_branch,
        client,
        node_group_schema,
        data_schema,
    ) -> None:
        """Test that we add locks for relationships where the peer has max_count constraint."""
        # Create a schema where:
        # - Team has a many relationship to Player
        # - Player has a many relationship back to Team with max_count=5
        # This tests the case where the peer limits how many nodes can link to it
        schema: dict[str, Any] = {
            "nodes": [
                {
                    "name": "Team",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "players",
                            "peer": "TestPlayer",
                            "cardinality": "many",
                            "identifier": "team__player",
                        },
                    ],
                },
                {
                    "name": "Player",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "teams",
                            "peer": "TestTeam",
                            "cardinality": "many",
                            "identifier": "team__player",
                            "max_count": 3,
                        },
                    ],
                },
            ],
        }
        schema_root = SchemaRoot(**schema)
        registry.schema.register_schema(schema=schema_root, branch=default_branch.name)
        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)

        # Create a player
        player = await create_and_save(db=db, schema="TestPlayer", name="John")

        # Create a team linked to that player
        team = await create_and_save(db=db, schema="TestTeam", name="Red Team", players=player)

        # The lock names should include the relationship_count lock for the player's ID
        lock_names = get_lock_names_on_object_mutation(team, schema_branch=schema_branch)

        expected_lock = f"{RELATIONSHIP_COUNT_LOCK_NAMESPACE}.team__player.{player.id}"
        assert expected_lock in lock_names

    async def test_lock_names_min_count_relationship(
        self,
        db: InfrahubDatabase,
        default_branch,
        client,
        node_group_schema,
        data_schema,
    ) -> None:
        """Test that we add locks for relationships where the peer has min_count constraint."""
        # Create a schema where:
        # - Department has a many relationship to Employee
        # - Employee has a many relationship back to Department with min_count=1
        # This tests the case where the peer requires a minimum number of links
        schema: dict[str, Any] = {
            "nodes": [
                {
                    "name": "Department",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "employees",
                            "peer": "TestEmployee",
                            "cardinality": "many",
                            "identifier": "department__employee",
                        },
                    ],
                },
                {
                    "name": "Employee",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "departments",
                            "peer": "TestDepartment",
                            "cardinality": "many",
                            "identifier": "department__employee",
                            "min_count": 1,
                        },
                    ],
                },
            ],
        }
        schema_root = SchemaRoot(**schema)
        registry.schema.register_schema(schema=schema_root, branch=default_branch.name)
        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)

        # Create an employee
        employee = await create_and_save(db=db, schema="TestEmployee", name="Alice")

        # Create a department linked to that employee
        department = await create_and_save(db=db, schema="TestDepartment", name="Engineering", employees=employee)

        # The lock names should include the relationship_count lock for the employee's ID
        lock_names = get_lock_names_on_object_mutation(department, schema_branch=schema_branch)

        expected_lock = f"{RELATIONSHIP_COUNT_LOCK_NAMESPACE}.department__employee.{employee.id}"
        assert expected_lock in lock_names

    async def test_lock_names_direct_min_count_relationship(
        self,
        db: InfrahubDatabase,
        default_branch,
        client,
        node_group_schema,
        data_schema,
    ) -> None:
        """Test that we add locks for direct min_count relationships on the node side."""
        # Create a schema where:
        # - Project has a many relationship to Member with min_count=2
        # - Member has a many relationship back to Project
        # This tests the case where the node being created has a min_count constraint
        schema: dict[str, Any] = {
            "nodes": [
                {
                    "name": "Project",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "members",
                            "peer": "TestMember",
                            "cardinality": "many",
                            "identifier": "project__member",
                            "min_count": 2,
                        },
                    ],
                },
                {
                    "name": "Member",
                    "namespace": "Test",
                    "default_filter": "name__value",
                    "branch": BranchSupportType.AWARE.value,
                    "attributes": [
                        {"name": "name", "kind": "Text"},
                    ],
                    "relationships": [
                        {
                            "name": "projects",
                            "peer": "TestProject",
                            "cardinality": "many",
                            "identifier": "project__member",
                        },
                    ],
                },
            ],
        }
        schema_root = SchemaRoot(**schema)
        registry.schema.register_schema(schema=schema_root, branch=default_branch.name)
        schema_branch = registry.schema.get_schema_branch(name=default_branch.name)

        # Create members
        member1 = await create_and_save(db=db, schema="TestMember", name="Bob")
        member2 = await create_and_save(db=db, schema="TestMember", name="Carol")

        # Create a project linked to members
        project = await create_and_save(db=db, schema="TestProject", name="Alpha", members=[member1, member2])

        # The lock names should include the relationship_count lock for the project's node ID
        lock_names = get_lock_names_on_object_mutation(project, schema_branch=schema_branch)

        expected_lock = f"{RELATIONSHIP_COUNT_LOCK_NAMESPACE}.project__member.{project.id}"
        assert expected_lock in lock_names

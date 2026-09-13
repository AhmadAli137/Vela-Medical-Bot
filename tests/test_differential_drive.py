"""Independent physical propulsion checks, including causal counterfactuals."""
import pytest
import mujoco

from sim.reference_drive_report import evaluate_raw_drive, route_contacts
from sim.reference_model import load_reference_model


@pytest.fixture(scope="module")
def measured():
    return evaluate_raw_drive()


def test_equal_and_opposite_wheels_produce_forward_motion_and_turning(measured):
    assert measured["checks"]["forward_travel_observed"]
    assert measured["checks"]["opposite_wheels_turn_observed"]
    assert measured["checks"]["small_body_lateral_slip"]
    assert measured["checks"]["rolling_forward_agreement"]
    assert measured["checks"]["rolling_yaw_agreement"]


def test_loaded_tire_contacts_supply_propulsion_without_base_actuator_forces(measured):
    assert measured["checks"]["both_tires_loaded"]
    assert measured["checks"]["contact_provides_forward_impulse"]
    assert measured["checks"]["no_direct_base_drive_force"]


def test_spinning_wheels_without_friction_cannot_translate_the_base(measured):
    assert measured["checks"]["frictionless_wheels_spin_without_base_propulsion"]


def test_disabling_motor_torque_prevents_the_same_drive_command_from_translating(measured):
    assert measured["checks"]["zero_motor_torque_prevents_propulsion"]


@pytest.mark.parametrize("body,support,command", [
    ("phone", "phone_delivery_riser", "deliver_phone_demo"),
    ("meal_box", "meal_delivery_riser", "deliver_meal_demo"),
])
def test_real_delivery_support_contact_is_allowed_only_for_its_delivery(body, support, command):
    model, data, _ = load_reference_model()
    support_id = model.geom(support).id
    object_id = model.geom(f"{body}_geom").id
    address = model.joint(f"{body}_free").qposadr[0]
    # Test fixture perturbation only: let the free object fall onto its actual
    # support; contact classification consumes solved forces, not named mocks.
    data.qpos[address:address + 3] = data.geom_xpos[support_id]
    data.qpos[address + 2] += model.geom_size[support_id, 2] + model.geom_size[object_id, 2] + .005
    for _ in range(500):
        mujoco.mj_step(model, data)
    mujoco.mj_forward(model, data)
    observed = route_contacts(model, data, "greeting_demo")
    assert any(support in event["geoms"] and event["normal_force_n"] > .1 for event in observed)
    assert not route_contacts(model, data, command)

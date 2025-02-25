# Copyright (c) Streamlit Inc. (2018-2022) Snowflake Inc. (2022-2024)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from enum import Enum, EnumMeta
from typing import TYPE_CHECKING, Any, Iterable, Sequence, overload

import streamlit
from streamlit import config, runtime, type_util
from streamlit.elements.form import is_in_form
from streamlit.errors import StreamlitAPIException, StreamlitAPIWarning
from streamlit.proto.LabelVisibilityMessage_pb2 import LabelVisibilityMessage
from streamlit.runtime.state import WidgetCallback, get_session_state
from streamlit.runtime.state.common import RegisterWidgetResult
from streamlit.type_util import T

if TYPE_CHECKING:
    from streamlit.delta_generator import DeltaGenerator


def check_callback_rules(dg: DeltaGenerator, on_change: WidgetCallback | None) -> None:
    if runtime.exists() and is_in_form(dg) and on_change is not None:
        raise StreamlitAPIException(
            "With forms, callbacks can only be defined on the `st.form_submit_button`."
            " Defining callbacks on other widgets inside a form is not allowed."
        )


_shown_default_value_warning: bool = False


def check_session_state_rules(
    default_value: Any, key: str | None, writes_allowed: bool = True
) -> None:
    global _shown_default_value_warning

    if key is None or not runtime.exists():
        return

    session_state = get_session_state()
    if not session_state.is_new_state_value(key):
        return

    if not writes_allowed:
        raise StreamlitAPIException(
            f'Values for the widget with key "{key}" cannot be set using `st.session_state`.'
        )

    if (
        default_value is not None
        and not _shown_default_value_warning
        and not config.get_option("global.disableWidgetStateDuplicationWarning")
    ):
        streamlit.warning(
            f'The widget with key "{key}" was created with a default value but'
            " also had its value set via the Session State API."
        )
        _shown_default_value_warning = True


class CachedWidgetWarning(StreamlitAPIWarning):
    def __init__(self):
        super().__init__(
            """
Your script uses a widget command in a cached function
(function decorated with `@st.cache_data` or `@st.cache_resource`).
This code will only be called when we detect a cache "miss",
which can lead to unexpected results.

How to fix this:
* Move all widget commands outside the cached function.
* Or, if you know what you're doing, use `experimental_allow_widgets=True`
in the cache decorator to enable widget replay and suppress this warning.
"""
        )


def check_cache_replay_rules() -> None:
    """Check if a widget is allowed to be used in the current context.
    More specifically, this checks if the current context is inside a
    cached function that disallows widget usage. If so, it raises a warning.

    If there are other similar checks in the future, we could extend this
    function to check for those as well. And rename it to check_widget_usage_rules.
    """
    if runtime.exists():
        from streamlit.runtime.scriptrunner.script_run_context import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx and ctx.disallow_cached_widget_usage:
            # We use an exception here to show a proper stack trace
            # that indicates to the user where the issue is.
            streamlit.exception(CachedWidgetWarning())


def get_label_visibility_proto_value(
    label_visibility_string: type_util.LabelVisibility,
) -> LabelVisibilityMessage.LabelVisibilityOptions.ValueType:
    """Returns one of LabelVisibilityMessage enum constants.py based on string value."""

    if label_visibility_string == "visible":
        return LabelVisibilityMessage.LabelVisibilityOptions.VISIBLE
    elif label_visibility_string == "hidden":
        return LabelVisibilityMessage.LabelVisibilityOptions.HIDDEN
    elif label_visibility_string == "collapsed":
        return LabelVisibilityMessage.LabelVisibilityOptions.COLLAPSED

    raise ValueError(f"Unknown label visibility value: {label_visibility_string}")


@overload
def maybe_coerce_enum(
    register_widget_result: RegisterWidgetResult[Enum],
    options: type[Enum],
    opt_sequence: Sequence[Any],
) -> RegisterWidgetResult[Enum]:
    ...


@overload
def maybe_coerce_enum(
    register_widget_result: RegisterWidgetResult[T],
    options: type_util.OptionSequence[T],
    opt_sequence: Sequence[T],
) -> RegisterWidgetResult[T]:
    ...


def maybe_coerce_enum(register_widget_result, options, opt_sequence):
    """Maybe Coerce a RegisterWidgetResult with an Enum member value to
    RegisterWidgetResult[option] if option is an EnumType, otherwise just return
    the original RegisterWidgetResult."""

    # If the value is not a Enum, return early
    if not isinstance(register_widget_result.value, Enum):
        return register_widget_result

    coerce_class: EnumMeta | None
    if isinstance(options, EnumMeta):
        coerce_class = options
    else:
        coerce_class = _extract_common_class_from_iter(opt_sequence)
        if coerce_class is None:
            return register_widget_result

    return RegisterWidgetResult(
        type_util.coerce_enum(register_widget_result.value, coerce_class),
        register_widget_result.value_changed,
    )


# slightly ugly typing because TypeVars with Generic Bounds are not supported
# (https://github.com/python/typing/issues/548)
@overload
def maybe_coerce_enum_sequence(
    register_widget_result: RegisterWidgetResult[list[T]],
    options: type_util.OptionSequence[T],
    opt_sequence: Sequence[T],
) -> RegisterWidgetResult[list[T]]:
    ...


@overload
def maybe_coerce_enum_sequence(
    register_widget_result: RegisterWidgetResult[tuple[T, T]],
    options: type_util.OptionSequence[T],
    opt_sequence: Sequence[T],
) -> RegisterWidgetResult[tuple[T, T]]:
    ...


def maybe_coerce_enum_sequence(register_widget_result, options, opt_sequence):
    """Maybe Coerce a RegisterWidgetResult with a sequence of Enum members as value
    to RegisterWidgetResult[Sequence[option]] if option is an EnumType, otherwise just return
    the original RegisterWidgetResult."""

    # If not all widget values are Enums, return early
    if not all(isinstance(val, Enum) for val in register_widget_result.value):
        return register_widget_result

    # Extract the class to coerce
    coerce_class: EnumMeta | None
    if isinstance(options, EnumMeta):
        coerce_class = options
    else:
        coerce_class = _extract_common_class_from_iter(opt_sequence)
        if coerce_class is None:
            return register_widget_result

    # Return a new RegisterWidgetResult with the coerced enum values sequence
    return RegisterWidgetResult(
        type(register_widget_result.value)(
            type_util.coerce_enum(val, coerce_class)
            for val in register_widget_result.value
        ),
        register_widget_result.value_changed,
    )


def _extract_common_class_from_iter(iterable: Iterable[Any]) -> Any:
    """Return the common class of all elements in a iterable if they share one.
    Otherwise, return None."""
    try:
        inner_iter = iter(iterable)
        first_class = type(next(inner_iter))
    except StopIteration:
        return None
    if all(type(item) is first_class for item in inner_iter):
        return first_class
    return None

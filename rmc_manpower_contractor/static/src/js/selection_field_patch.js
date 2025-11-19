/** @odoo-module **/

import { SelectionField } from "@web/views/fields/selection/selection_field";
import { BadgeSelectionField } from "@web/views/fields/badge_selection/badge_selection_field";

const FALLBACK_STRING = (field) => {
    const value = field.props.record.data[field.props.name];
    if (value === undefined || value === null || value === false) {
        return "";
    }
    const option = field.options && field.options.find((opt) => opt[0] === value);
    return option ? option[1] : value;
};

Object.defineProperty(SelectionField.prototype, "string", {
    get() {
        return FALLBACK_STRING(this);
    },
});

Object.defineProperty(BadgeSelectionField.prototype, "string", {
    get() {
        return FALLBACK_STRING(this);
    },
});

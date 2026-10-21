// Cherry MX keycap generator with a text legend on top.
// Dimensions are taken from special_keycaps.3mf (Bambu Parametric Model Maker).
// Open in OpenSCAD and use the Customizer (Window > Customizer) to change values.

/* [Legend] */
legend          = "A";
// Any font installed on your system, e.g. "Liberation Sans:style=Bold"
font            = "Liberation Sans:style=Bold";
font_size       = 6;
// embossed = raised, debossed = engraved, inlay = flush (separate body for multi-colour), none
legend_mode     = "inlay"; // [embossed, debossed, inlay, none]
legend_depth    = 0.3;
legend_rotation = 0;
legend_offset   = [0, 0];

/* [Size] */
// Key width in units (1, 1.25, 1.5, 2, 2.25, ...)
units           = 1;
unit_pitch      = 19.05;
// Which part to output (inlay mode: export "cap" and "legend" separately as one multi-part object)
part            = "all"; // [all, cap, legend]
// Flip so the top sits on the bed, like the reference print
print_orientation = true;

/* [Shape] */
height          = 7.5;
base_size       = 18;     // 1u outer size at the base
top_size        = 14;     // 1u outer size at the top
base_radius     = 2;
top_radius      = 2;
top_thickness   = 1;
wall_thickness  = 1.5;    // at the base; tapers to `top_wall` at the top
top_wall        = 1;

/* [Stem] */
stem_diameter   = 5.5;
cross_length    = 4.25;
cross_width     = 1.25;
// Extra clearance added to the cross slot (increase if too tight)
cross_tolerance = 0;
// Stem stops this far above the rim
stem_recess     = 1;
// Extra stems for wide keys (2u+), Cherry stabilizer spacing from centre
stabilizers     = "auto"; // [auto, none]

/* [Hidden] */
$fn  = 64;
eps  = 0.01;
extra_w = (units - 1) * unit_pitch;

function stab_offset(u) =
    u >= 6.25 ? 50 :
    u >= 3    ? 19.05 :
    u >= 2    ? 11.938 : 0;

module rrect(w, d, r) {
    offset(r = r) square([w - 2 * r, d - 2 * r], center = true);
}

// Tapered rounded box: bottom at z=0, top at z=h
module frustum(bw, bd, br, tw, td, tr, h) {
    hull() {
        linear_extrude(eps) rrect(bw, bd, br);
        translate([0, 0, h - eps]) linear_extrude(eps) rrect(tw, td, tr);
    }
}

module shell() {
    bw = base_size + extra_w;  tw = top_size + extra_w;
    difference() {
        frustum(bw, base_size, base_radius, tw, top_size, top_radius, height);
        translate([0, 0, -eps])
            frustum(bw - 2 * wall_thickness, base_size - 2 * wall_thickness,
                    max(base_radius - wall_thickness, 0.5),
                    tw - 2 * top_wall, top_size - 2 * top_wall,
                    max(top_radius - top_wall, 0.5),
                    height - top_thickness + eps);
    }
}

module stem() {
    l = cross_length + cross_tolerance;
    w = cross_width + cross_tolerance;
    translate([0, 0, stem_recess])
    difference() {
        cylinder(d = stem_diameter, h = height - stem_recess - top_thickness + eps);
        translate([0, 0, -eps]) linear_extrude(height) {
            square([l, w], center = true);
            square([w, l], center = true);
        }
    }
}

module stems() {
    stem();
    s = stab_offset(units);
    if (stabilizers == "auto" && s > 0)
        for (x = [-s, s]) translate([x, 0, 0]) stem();
}

module legend_2d() {
    translate(legend_offset) rotate(legend_rotation)
        text(legend, size = font_size, font = font,
             halign = "center", valign = "center");
}

module legend_body(z0, h) {
    translate([0, 0, z0]) linear_extrude(h) legend_2d();
}

module cap() {
    difference() {
        union() { shell(); stems(); }
        if (legend_mode == "debossed" || legend_mode == "inlay")
            legend_body(height - legend_depth, legend_depth + eps);
    }
}

module legend_part() {
    if (legend_mode == "inlay")
        legend_body(height - legend_depth, legend_depth);
    else if (legend_mode == "embossed")
        legend_body(height - eps, legend_depth + eps);
}

module orient() {
    if (print_orientation)
        translate([0, 0, height + (legend_mode == "embossed" ? legend_depth : 0)])
            rotate([180, 0, 0]) children();
    else children();
}

orient() {
    if (part == "all" || part == "cap") color("DimGray") cap();
    if ((part == "all" || part == "legend") && legend_mode != "none" && legend != "")
        color("White") legend_part();
}

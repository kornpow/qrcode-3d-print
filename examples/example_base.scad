            // Base plate
            difference() {
                hull() {
    translate([10.0,   10.0,   0]) cylinder(h=3.0, r=10.0, $fn=64);
    translate([58.8, 10.0,   0]) cylinder(h=3.0, r=10.0, $fn=64);
    translate([10.0,   84.2, 0]) cylinder(h=3.0, r=10.0, $fn=64);
    translate([58.8, 84.2, 0]) cylinder(h=3.0, r=10.0, $fn=64);
}
translate([34.4000, 89.2000, -1])
    cylinder(h=5.0, r=4.0, $fn=64);
            }

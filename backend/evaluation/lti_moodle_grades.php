<?php
// Test-only: let the Adaptive LMS tool send grades (LTI Assignment and Grade Services) and create grade columns.
define('CLI_SCRIPT', true);
require('/var/www/html/config.php');
require_once($CFG->dirroot . '/mod/lti/locallib.php');

$typeid = $DB->get_field('lti_types', 'id', ['name' => 'Adaptive LMS'], MUST_EXIST);
$settings = [
    'acceptgrades' => LTI_SETTING_ALWAYS,
    'ltiservice_gradesynchronization' => 2,  // grade sync and column management
    'keytype' => LTI_JWK_KEYSET,
    'publickeyset' => 'http://localhost:8080/api/v1/lti/jwks',
];
foreach ($settings as $name => $value) {
    $row = $DB->get_record('lti_types_config', ['typeid' => $typeid, 'name' => $name]);
    if ($row) {
        $DB->set_field('lti_types_config', 'value', $value, ['id' => $row->id]);
    } else {
        $DB->insert_record('lti_types_config', (object) ['typeid' => $typeid, 'name' => $name, 'value' => $value]);
    }
}
purge_all_caches();
$lines = [];
foreach ($DB->get_records('lti_types_config', ['typeid' => $typeid]) as $r) {
    if (array_key_exists($r->name, $settings)) {
        $lines[$r->name] = $r->value;
    }
}
echo json_encode(['typeid' => $typeid, 'settings' => $lines]) . "\n";

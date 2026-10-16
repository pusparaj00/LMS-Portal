<?php
// Test-only Moodle setup for the Adaptive LMS LTI 1.3 gate (TR-A-09). Run inside the moodle-docker webserver:
//   copy it to the Moodle folder, then: TEACHER_PW=... STUDENT_PW=... php setup_lti.php (see docs/results/step-13.md)
define('CLI_SCRIPT', true);
$root = is_file('/var/www/html/config.php') ? '/var/www/html' : dirname(__DIR__);
require($root . '/config.php');
require_once($CFG->dirroot . '/mod/lti/locallib.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/course/modlib.php');
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->libdir . '/enrollib.php');

\core\session\manager::set_user(get_admin());
$tool = 'http://localhost:8080';

$typeid = $DB->get_field('lti_types', 'id', ['name' => 'Adaptive LMS']);
if (!$typeid) {
    $type = new stdClass();
    $type->state = LTI_TOOL_STATE_CONFIGURED;
    $type->name = 'Adaptive LMS';
    $type->baseurl = $tool . '/';
    $type->coursevisible = LTI_COURSEVISIBLE_ACTIVITYCHOOSER;
    $type->ltiversion = LTI_VERSION_1P3;
    $config = new stdClass();
    $config->lti_ltiversion = LTI_VERSION_1P3;
    $config->lti_toolurl = $tool . '/';
    $config->lti_initiatelogin = $tool . '/api/v1/lti/login';
    $config->lti_redirectionuris = $tool . '/api/v1/lti/launch';
    $config->lti_keytype = LTI_JWK_KEYSET;
    // Moodle requires a key set for the tool; nothing here calls Moodle's services, so it is never fetched.
    $config->lti_publickeyset = $tool . '/api/v1/lti/jwks-not-used';
    $config->lti_launchcontainer = LTI_LAUNCH_CONTAINER_WINDOW;
    $config->lti_sendname = LTI_SETTING_NEVER;
    $config->lti_sendemailaddr = LTI_SETTING_NEVER;
    $config->lti_acceptgrades = LTI_SETTING_NEVER;
    $config->lti_coursevisible = LTI_COURSEVISIBLE_ACTIVITYCHOOSER;
    $typeid = lti_add_type($type, $config);
}
$clientid = $DB->get_field('lti_types', 'clientid', ['id' => $typeid]);

$course = $DB->get_record('course', ['shortname' => 'PY101']);
if (!$course) {
    $course = create_course((object) ['fullname' => 'Python 101 (Moodle)', 'shortname' => 'PY101', 'category' => 1]);
}
$manual = enrol_get_plugin('manual');
$instance = $DB->get_record('enrol', ['courseid' => $course->id, 'enrol' => 'manual'], '*', MUST_EXIST);
foreach (['teacher1' => ['editingteacher', 'TEACHER_PW'], 'student1' => ['student', 'STUDENT_PW']] as $name => [$role, $env]) {
    $user = $DB->get_record('user', ['username' => $name]);
    if (!$user) {
        $id = user_create_user((object) [
            'username' => $name, 'password' => getenv($env), 'firstname' => ucfirst($name), 'lastname' => 'Test',
            'email' => $name . '@example.invalid', 'auth' => 'manual', 'confirmed' => 1,
            'mnethostid' => $CFG->mnet_localhost_id,
        ]);
        $user = $DB->get_record('user', ['id' => $id]);
    }
    $manual->enrol_user($instance, $user->id, $DB->get_field('role', 'id', ['shortname' => $role]));
}

$cmid = $DB->get_field_sql(
    "SELECT cm.id FROM {course_modules} cm JOIN {modules} m ON m.id = cm.module AND m.name = 'lti' WHERE cm.course = ?",
    [$course->id], IGNORE_MULTIPLE
);
if (!$cmid) {
    $info = (object) [
        'modulename' => 'lti', 'course' => $course->id, 'section' => 0, 'visible' => 1, 'name' => 'Adaptive LMS',
        'typeid' => $typeid, 'toolurl' => '', 'securetoolurl' => '', 'launchcontainer' => LTI_LAUNCH_CONTAINER_WINDOW,
        'instructorchoicesendname' => 0, 'instructorchoicesendemailaddr' => 0, 'instructorchoiceacceptgrades' => 0,
        'grade' => 0, 'introeditor' => ['text' => '', 'format' => FORMAT_HTML, 'itemid' => 0],
    ];
    $cmid = create_module($info)->coursemodule;
}
echo json_encode(['typeid' => (string) $typeid, 'clientid' => $clientid, 'courseid' => $course->id, 'cmid' => $cmid,
    'issuer' => $CFG->wwwroot]) . "\n";

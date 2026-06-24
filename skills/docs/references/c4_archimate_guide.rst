C4 Model and ArchiMate Reference
=================================

.. contents:: Contents
   :depth: 2
   :local:

----

C4 Model
--------

The C4 model (Simon Brown) provides four levels of zoom. This skill covers
the first three.

Level 1 — System Context
~~~~~~~~~~~~~~~~~~~~~~~~~

**Question**: What does the system do, and who/what interacts with it?

PlantUML include::

   !include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Context.puml

.. list-table:: Elements
   :header-rows: 1
   :widths: 20 35 45

   * - Macro
     - Signature
     - Use when
   * - ``Person``
     - ``Person(alias, "Name", "Desc")``
     - Human user of the system
   * - ``Person_Ext``
     - ``Person_Ext(alias, "Name", "Desc")``
     - Human user outside the boundary
   * - ``System``
     - ``System(alias, "Name", "Desc")``
     - The system in scope
   * - ``System_Ext``
     - ``System_Ext(alias, "Name", "Desc")``
     - External system (out of scope)
   * - ``System_Boundary``
     - ``System_Boundary(alias, "Name") { }``
     - Logical boundary wrapper

Level 2 — Containers
~~~~~~~~~~~~~~~~~~~~~

**Question**: What are the major deployable units inside the system boundary?

A *container* is anything that can be deployed independently: web app,
mobile app, microservice, database, message queue, file store.

PlantUML include::

   !include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Container.puml

.. list-table:: Elements
   :header-rows: 1
   :widths: 20 45 35

   * - Macro
     - Signature
     - Use when
   * - ``Container``
     - ``Container(alias, "Name", "Tech", "Desc")``
     - Application or service
   * - ``ContainerDb``
     - ``ContainerDb(alias, "Name", "Tech", "Desc")``
     - Database or data store
   * - ``ContainerQueue``
     - ``ContainerQueue(alias, "Name", "Tech", "Desc")``
     - Message broker or queue
   * - ``Container_Boundary``
     - ``Container_Boundary(alias, "Name") { }``
     - Groups containers in a boundary

Level 3 — Components
~~~~~~~~~~~~~~~~~~~~~

**Question**: What are the major structural building blocks inside one container?

A *component* maps to a module, class group, or major interface within a
container — not every class, only groupings with distinct responsibilities.

PlantUML include::

   !include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Component.puml

.. list-table:: Elements
   :header-rows: 1
   :widths: 20 45 35

   * - Macro
     - Signature
     - Use when
   * - ``Component``
     - ``Component(alias, "Name", "Tech", "Desc")``
     - Logical component
   * - ``ComponentDb``
     - ``ComponentDb(alias, "Name", "Tech", "Desc")``
     - Data access component
   * - ``Container_Boundary``
     - ``Container_Boundary(alias, "Name") { }``
     - Wraps the container being zoomed into

C4 Relationship Macros
~~~~~~~~~~~~~~~~~~~~~~~

These macros apply across all three levels::

   Rel(from, to, "label")
   Rel(from, to, "label", "technology")
   BiRel(a, b, "label")

Always end C4 diagrams with ``SHOW_LEGEND()``.

C4 Best Practices
~~~~~~~~~~~~~~~~~

- Start with System Context before drilling into Containers or Components.
- One container = one independently deployable unit.
- One Component diagram per container (separate file per container).
- Only show relationships that cross a boundary — not internal implementation.
- Document technology choices explicitly in the *Tech* field.

----

ArchiMate
---------

ArchiMate (The Open Group) is an enterprise architecture notation covering
three layers: Business, Application, Technology. It complements C4 by
providing enterprise-scope views that span system boundaries.

PlantUML uses the built-in stdlib — no external URL needed::

   !include <archimate/ArchiMate>

Business Layer
~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Macro
     - Purpose
   * - ``Business_Actor(alias, "Name")``
     - Person or organisation that performs behaviour
   * - ``Business_Role(alias, "Name")``
     - Responsibility assigned to an actor
   * - ``Business_Process(alias, "Name")``
     - Sequence of business behaviours
   * - ``Business_Function(alias, "Name")``
     - Business capability (non-sequential)
   * - ``Business_Service(alias, "Name")``
     - Externally visible business behaviour
   * - ``Business_Object(alias, "Name")``
     - Concept used in business (passive)
   * - ``Business_Interaction(alias, "Name")``
     - Behaviour performed by multiple roles
   * - ``Business_Event(alias, "Name")``
     - Business-layer event

Application Layer
~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Macro
     - Purpose
   * - ``Application_Component(alias, "Name")``
     - Modular unit of application functionality
   * - ``Application_Service(alias, "Name")``
     - Externally visible unit of functionality
   * - ``Application_Interface(alias, "Name")``
     - Point of access for application services
   * - ``Application_Function(alias, "Name")``
     - Automated behaviour of a component
   * - ``Application_DataObject(alias, "Name")``
     - Data managed by the application (passive)
   * - ``Application_Interaction(alias, "Name")``
     - Behaviour of two or more components

Technology Layer
~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Macro
     - Purpose
   * - ``Technology_Node(alias, "Name")``
     - Computational or physical resource
   * - ``Technology_SystemSoftware(alias, "Name")``
     - Software environment (OS, DBMS, middleware)
   * - ``Technology_TechnologyService(alias, "Name")``
     - Externally visible technology behaviour
   * - ``Technology_Artifact(alias, "Name")``
     - Physical piece of data (JAR, Docker image, file)
   * - ``Technology_CommunicationNetwork(alias, "Name")``
     - Network connecting nodes

Motivation Layer (cross-cutting)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Macro
     - Purpose
   * - ``Motivation_Stakeholder(alias, "Name")``
     - Stakeholder with interests
   * - ``Motivation_Driver(alias, "Name")``
     - External or internal condition motivating change
   * - ``Motivation_Goal(alias, "Name")``
     - End state a stakeholder wants to achieve
   * - ``Motivation_Requirement(alias, "Name")``
     - Need that must be met
   * - ``Motivation_Constraint(alias, "Name")``
     - Factor that limits a solution

ArchiMate Relationships
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Macro
     - Meaning
   * - ``Rel_Association(a, b, "label")``
     - Generic, unspecified relationship
   * - ``Rel_Serving(a, b, "label")``
     - ``a`` provides a service to ``b``
   * - ``Rel_Triggering(a, b, "label")``
     - ``a`` triggers ``b``
   * - ``Rel_Flow(a, b, "label")``
     - Information or value flows from ``a`` to ``b``
   * - ``Rel_Realization(a, b, "label")``
     - ``a`` realizes the more abstract ``b``
   * - ``Rel_Assignment(a, b, "label")``
     - Active element ``a`` is assigned to behaviour ``b``
   * - ``Rel_Composition(a, b, "label")``
     - ``b`` is composed into ``a`` (strong whole-part)
   * - ``Rel_Aggregation(a, b, "label")``
     - ``b`` is aggregated into ``a`` (weak whole-part)
   * - ``Rel_Influence(a, b, "label")``
     - Motivation layer: ``a`` influences ``b``
   * - ``Rel_Access(a, b, "label")``
     - ``a`` reads or writes ``b``

ArchiMate Best Practices
~~~~~~~~~~~~~~~~~~~~~~~~~

- Use one diagram per *view* (stakeholder concern), not one diagram for everything.
- Layer boundaries matter: keep Business / Application / Technology distinct;
  bridge them only with ``Rel_Serving``, ``Rel_Realization``, or ``Rel_Assignment``.
- The Motivation layer sits above Business and can reference any layer.
- Combine ArchiMate for enterprise scope with C4 for software detail: ArchiMate
  describes the landscape, C4 describes the internals of individual systems.

----

RST Image Directive
-------------------

All diagrams are pre-rendered to SVG and included in RST pages with::

   .. image:: diagrams/<name>.svg
      :alt: <descriptive alt text>
      :align: center
      :width: 100%

The ``:width: 100%`` ensures the SVG scales to the page width, which is
the main scalability advantage over inline rendering.

For component pages (one level deeper in the directory tree), adjust the
relative path accordingly::

   .. image:: ../diagrams/components_<name>.svg
      :alt: Component Diagram: <Container Name>
      :align: center
      :width: 100%

----

Common Mistakes
---------------

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Mistake
     - Fix
   * - Implementation detail in Context diagram
     - Keep Context to external actors and systems only
   * - Every class as a Component
     - Only model groupings with distinct responsibilities
   * - Mixing levels in one diagram
     - One diagram = one level of zoom
   * - ArchiMate elements from wrong layer
     - Match element type to the layer where the concept lives
   * - Missing ``SHOW_LEGEND()`` in C4 diagrams
     - Always call ``SHOW_LEGEND()`` at the end
   * - Forgetting to re-render after editing ``.puml``
     - Run ``generate_diagrams.py`` after every diagram change

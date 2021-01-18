import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import microdf as mdf

person = pd.read_csv(
    "https://github.com/MaxGhenis/datarepo/raw/master/pppub20.csv.gz",
    usecols=[
        "MARSUPWT",
        "SPM_ID",
        "SPM_POVTHRESHOLD",
        "SPM_RESOURCES",
        "A_AGE",
        "TAX_INC",
        "SPM_WEIGHT",
        "SPM_NUMPER",
    ],
)

# Lower column headers and adapt weights
person.columns = person.columns.str.lower()
person["person_weight"] = person.marsupwt / 100
person.spm_weight /= 100

# Determine age demographic
person["child"] = person.a_age < 18
person["adult"] = person.a_age > 17

# calculate population statistics
adult_pop = (person.adult * person.person_weight).sum()
child_pop = (person.child * person.person_weight).sum()
pop = child_pop + adult_pop

# Create SPMU dataframe
spmu = (
    person.groupby(
        ["spm_id", "spm_weight", "spm_povthreshold", "spm_resources", "spm_numper"]
    )[["child", "adult", "tax_inc"]]
    .sum()
    .reset_index()
)

total_taxable_income = (spmu.tax_inc * spmu.spm_weight).sum()


def pov_gap(df, resources, threshold, weight):
    gaps = np.maximum(df[threshold] - df[resources], 0)
    return (gaps * df[weight]).sum()


def ubi(funding_billions=0, child_percent_funding=0):
    funding = funding_billions * 1e9
    child_percent_funding /= 100
    adult_ubi = ((1 - child_percent_funding) * funding) / adult_pop
    child_ubi = (child_percent_funding * funding) / child_pop

    tax_rate = funding / total_taxable_income

    spmu["new_tax"] = tax_rate * spmu.tax_inc
    spmu["spm_ubi"] = (spmu.child * child_ubi) + (spmu.adult * adult_ubi)

    spmu["new_spm_resources"] = spmu.spm_resources + spmu.spm_ubi - spmu.new_tax
    spmu["new_spm_resources_pp"] = spmu.new_spm_resources / spmu.spm_numper

    # Calculate poverty gap
    poverty_gap = pov_gap(spmu, "new_spm_resources", "spm_povthreshold", "spm_weight")

    # Merge person and spmu dataframes
    spmu_sub = spmu[["spm_id", "new_spm_resources", "new_spm_resources_pp"]]
    target_persons = pd.merge(spmu_sub, person, on=["spm_id"])

    target_persons["poor"] = (
        target_persons.new_spm_resources < target_persons.spm_povthreshold
    )
    total_poor = (target_persons.poor * target_persons.person_weight).sum()
    poverty_rate = total_poor / pop * 100

    # Calculate Gini
    gini = mdf.gini(target_persons, "new_spm_resources_pp", w="person_weight")

    # Percent winners
    target_persons["better_off"] = (
        target_persons.new_spm_resources > target_persons.spm_resources
    )
    total_better_off = (target_persons.better_off * target_persons.person_weight).sum()
    percent_better_off = total_better_off / pop

    return pd.Series(
        [poverty_rate, gini, poverty_gap, percent_better_off, adult_ubi, child_ubi]
    )


def ubi2(funding_billions=0, child_percent_ubi=0):
    funding = funding_billions * 1e9
    child_percent_ubi /= 100
    adult_ubi = funding / (adult_pop + (child_pop * child_percent_ubi))
    child_ubi = adult_ubi * child_percent_ubi

    tax_rate = funding / total_taxable_income

    spmu["new_tax"] = tax_rate * spmu.tax_inc
    spmu["spm_ubi"] = (spmu.child * child_ubi) + (spmu.adult * adult_ubi)

    spmu["new_spm_resources"] = spmu.spm_resources + spmu.spm_ubi - spmu.new_tax
    spmu["new_spm_resources_pp"] = spmu.new_spm_resources / spmu.spm_numper

    # Calculate poverty gap
    poverty_gap = pov_gap(spmu, "new_spm_resources", "spm_povthreshold", "spm_weight")

    # Merge person and spmu dataframes
    spmu_sub = spmu[["spm_id", "new_spm_resources", "new_spm_resources_pp"]]
    target_persons = pd.merge(spmu_sub, person, on=["spm_id"])

    target_persons["poor"] = (
        target_persons.new_spm_resources < target_persons.spm_povthreshold
    )
    total_poor = (target_persons.poor * target_persons.person_weight).sum()
    poverty_rate = total_poor / pop * 100

    # Calculate Gini
    gini = mdf.gini(target_persons, "new_spm_resources_pp", w="person_weight")

    # Percent winners
    target_persons["better_off"] = (
        target_persons.new_spm_resources > target_persons.spm_resources
    )
    total_better_off = (target_persons.better_off * target_persons.person_weight).sum()
    percent_better_off = total_better_off / pop

    return pd.Series(
        [poverty_rate, gini, poverty_gap, percent_better_off, adult_ubi, child_ubi]
    )


# create a dataframe with all possible combinations of funding levels and
summary = mdf.cartesian_product(
    {
        "funding_billions": np.arange(0, 3_001, 50),
        "child_percent_funding": np.arange(0, 101, 1),
    }
)


def ubi_row(row):
    return ubi(row.funding_billions, row.child_percent_funding)


summary[
    [
        "poverty_rate",
        "gini",
        "poverty_gap",
        "percent_better_off",
        "adult_ubi",
        "child_ubi",
    ]
] = summary.apply(ubi_row, axis=1)

summary["monthly_child_ubi"] = summary["child_ubi"].apply(
    lambda x: int(round(x / 12, 0))
)
summary["monthly_adult_ubi"] = summary["adult_ubi"].apply(
    lambda x: int(round(x / 12, 0))
)
summary.to_csv("children_share_funding_summary.csv.gz", compression="gzip")

# drop rows where funding level is 0
optimal_poverty = summary.sort_values("poverty_gap").drop_duplicates(
    "funding_billions", keep="first"
)
optimal_poverty = optimal_poverty.drop(
    optimal_poverty[optimal_poverty.funding_billions == 0].index
)

optimal_inequality = summary.sort_values("gini").drop_duplicates(
    "funding_billions", keep="first"
)
optimal_inequality = optimal_inequality.drop(
    optimal_inequality[optimal_inequality.funding_billions == 0].index
)

optimal_winners = summary.sort_values("percent_better_off").drop_duplicates(
    "funding_billions", keep="last"
)
optimal_winners = optimal_winners.drop(
    optimal_winners[optimal_winners.funding_billions == 0].index
)

summary2 = mdf.cartesian_product(
    {
        "funding_billions": np.arange(0, 3_001, 50),
        "child_percent_ubi": np.arange(0, 101, 50),
    }
)


def big_percent_row(row):
    return ubi2(row.funding_billions, row.child_percent_ubi)


summary2[
    [
        "poverty_rate",
        "gini",
        "poverty_gap",
        "percent_better_off",
        "adult_ubi",
        "child_ubi",
    ]
] = summary2.apply(big_percent_row, axis=1)
summary2

# calculate monthly payments
summary2["monthly_child_ubi"] = summary2["child_ubi"].apply(
    lambda x: int(round(x / 12, 0))
)
summary2["monthly_adult_ubi"] = summary2["adult_ubi"].apply(
    lambda x: int(round(x / 12, 0))
)
summary2.sample(10)
summary2.to_csv("children_share_ubi_summary.csv.gz", compression="gzip")

summary2.to_csv("child_share_ubi_summary.csv.gz", compression="gzip")

"""# Old Chart"""

### LOAD DATA ###

person_raw = pd.read_csv(
    "https://github.com/MaxGhenis/datarepo/raw/master/pppub20.csv.gz",
    usecols=["MARSUPWT", "SPM_ID", "SPM_POVTHRESHOLD", "SPM_RESOURCES", "A_AGE"],
)

### PREPROCESS ###

person = person_raw.copy(deep=True)
person.columns = person.columns.str.lower()
person["weight"] = person.marsupwt / 100
# Compute total children and adults in each resource sharing group.
person["child"] = person.a_age < 18
person["adult"] = person.a_age >= 18
spmu_ages = person.groupby("spm_id")[["child", "adult"]].sum()
spmu_ages.columns = ["children", "total_adults"]
person2 = person.merge(spmu_ages, left_on="spm_id", right_index=True)
total_children = (person2.child * person2.weight).sum()
total_adults = (person2.adult * person2.weight).sum()

### CALCULATIONS ###

child_allowance_overall = []
child_allowance_child = []
child_allowance_adults = []

# Determine the poverty rate impact of a Child Allownace from $0 in new spending to $1 trillion.

for spending in range(0, 1000000000001, 50000000000):
    child_allowance_per_child = spending / total_children
    total_child_allowance = person2.children * child_allowance_per_child
    new_spm_resources_ca = person2.spm_resources + total_child_allowance
    new_poor_ca = new_spm_resources_ca < person2.spm_povthreshold
    new_total_child_poor = (person2.child * person2.weight * new_poor_ca).sum()
    new_child_poverty_rate = (new_total_child_poor) / (
        person2.child * person2.weight
    ).sum()
    new_total_adult_poor = (person2.adult * person2.weight * new_poor_ca).sum()
    new_adult_poverty_rate = (new_total_adult_poor) / (
        person2.adult * person2.weight
    ).sum()
    new_total_poor_ca = (new_poor_ca * person2.weight).sum()
    new_poverty_rate_ca = new_total_poor_ca / person2.weight.sum()
    child_allowance_overall.append(new_poverty_rate_ca)
    child_allowance_child.append(new_child_poverty_rate)
    child_allowance_adults.append(new_adult_poverty_rate)

ubi_adults_overall = []
ubi_adults_child = []
ubi_adults_adults = []

# Determine the poverty rate impact of a Adult UBI from $0 in new spending to $1 trillion.

for spending in range(0, 1000000000001, 50000000000):
    adult_ubi = spending / total_adults
    total_adult_ubi = person2.total_adults * adult_ubi
    new_spm_resources_ubi = person2.spm_resources + total_adult_ubi
    new_poor_ubi = new_spm_resources_ubi < person2.spm_povthreshold
    new_total_child_poor = (person2.child * person2.weight * new_poor_ubi).sum()
    new_child_poverty_rate = (new_total_child_poor) / (
        person2.child * person2.weight
    ).sum()
    new_total_adult_poor = (person2.adult * person2.weight * new_poor_ubi).sum()
    new_adult_poverty_rate = (new_total_adult_poor) / (
        person2.adult * person2.weight
    ).sum()
    new_total_poor_ubi = (new_poor_ubi * person2.weight).sum()
    new_poverty_rate_ubi = new_total_poor_ubi / person2.weight.sum()
    ubi_adults_overall.append(new_poverty_rate_ubi)
    ubi_adults_child.append(new_child_poverty_rate)
    ubi_adults_adults.append(new_adult_poverty_rate)

ubi_all_overall = []
ubi_all_child = []
ubi_all_adults = []

# Determine the poverty rate impact of a All UBI from $0 in new spending to $1 trillion.

for spending in range(0, 1000000000001, 50000000000):
    all_ubi_per_person = spending / (total_adults + total_children)
    total_all_ubi = (person2.children * all_ubi_per_person) + (
        person2.total_adults * all_ubi_per_person
    )
    new_spm_resources_all_ubi = person2.spm_resources + total_all_ubi
    new_poor_all_ubi = new_spm_resources_all_ubi < person2.spm_povthreshold
    new_total_child_poor = (person2.child * person2.weight * new_poor_all_ubi).sum()
    new_child_poverty_rate = (new_total_child_poor) / (
        person2.child * person2.weight
    ).sum()
    new_total_adult_poor = (person2.adult * person2.weight * new_poor_all_ubi).sum()
    new_adult_poverty_rate = (new_total_adult_poor) / (
        person2.adult * person2.weight
    ).sum()
    new_total_poor_all_ubi = (new_poor_all_ubi * person2.weight).sum()
    new_poverty_rate_all_ubi = new_total_poor_all_ubi / person2.weight.sum()
    ubi_all_overall.append(new_poverty_rate_all_ubi)
    ubi_all_child.append(new_child_poverty_rate)
    ubi_all_adults.append(new_adult_poverty_rate)

spending_data = []
for spending in range(0, 1001, 50):
    spending = spending / 100
    spending_data.append(spending)

### ANALYSIS ###

# Create a DataFrame grouped by each plans impact on the overall poverty rate.
overall = {
    "spending_in_billions": spending_data,
    "child_allowance": child_allowance_overall,
    "adult_ubi": ubi_adults_overall,
    "all_ubi": ubi_all_overall,
}

overall_df = pd.DataFrame(overall)
overall_df = pd.DataFrame(overall_df).round(3)

# Create a DataFrame grouped by each plans impact on the child poverty rate.
child = {
    "spending_in_billions": spending_data,
    "child_allowance": child_allowance_child,
    "adult_ubi": ubi_adults_child,
    "all_ubi": ubi_all_child,
}

child_df = pd.DataFrame(child)
child_df = pd.DataFrame(child_df).round(3)


# Create a DataFrame grouped by each plans impact on the adult poverty rate.
adult = {
    "spending_in_billions": spending_data,
    "child_allowance": child_allowance_adults,
    "adult_ubi": ubi_adults_adults,
    "all_ubi": ubi_all_adults,
}

adult_df = pd.DataFrame(adult)
adult_df = pd.DataFrame(adult_df).round(3)


# Join different programs together for plotly.
program = pd.melt(
    overall_df, "spending_in_billions", var_name="ubi_type", value_name="poverty_rate"
)


def melt_dict(d):
    """produce long version of data frame represented by dictionary (d).

    Arguments
    d: Dictionary where each element represents a differnt UBI type and spending levels and the poverty impacts.

    Returns
    DataFrame where every row is the combination of UBI type and spending level.
    """
    df = pd.DataFrame(d).round(3) * 100
    program = pd.melt(
        df, "spending_in_billions", var_name="ubi_type", value_name="poverty_rate"
    )
    program["ubi_type"] = program.ubi_type.map(
        {
            "child_allowance": "Child allowance",
            "adult_ubi": "Adult UBI",
            "all_ubi": "All UBI",
        }
    )
    return program


program_overall = melt_dict(overall)
program_child = melt_dict(child)
program_adult = melt_dict(adult)


def line_graph(df, x, y, color, title, xaxis_title, yaxis_title):
    """Style for line graphs.

    Arguments
    df: DataFrame with data to be plotted.
    x: The string representing the column in df that holds the new spending in billions.
    y: The string representing the column in df that holds the poverty rate.
    color: The string representing the UBI type.
    xaxis_title: The string represnting the xaxis-title.
    yaxis_title: The string representing the yaxis-title.

    Returns
    Nothing. Shows the plot.
    """
    fig = px.line(df, x=x, y=y, color=color)
    fig.update_layout(
        title=title,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        yaxis_ticksuffix="%",
        font=dict(family="Roboto"),
        hovermode="x",
        xaxis_tickprefix="$",
        xaxis_ticksuffix="B",
        plot_bgcolor="white",
        legend_title_text="",
    )

    fig.update_traces(mode="markers+lines", hovertemplate=None)

    fig.show()


line_graph(
    df=program_overall,
    x="spending_in_billions",
    y="poverty_rate",
    color="ubi_type",
    title="Overall poverty rate and spending on cash transfer programs",
    xaxis_title="Spending in billions",
    yaxis_title="SPM poverty rate",
)

program_overall.to_csv("july_2020.csv")
